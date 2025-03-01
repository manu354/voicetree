import logging
import time
import traceback
import re
import asyncio
from collections import namedtuple
from typing import Set, Tuple, List

import google.generativeai as genai

import settings
from tree_manager.LLM_engine.background_rewrite import Rewriter
from tree_manager.LLM_engine.summarize_with_llm import Summarizer
from tree_manager.LLM_engine.tree_action_decider import Decider
from tree_manager.decision_tree_ds import DecisionTree
from tree_manager.utils import extract_summary, remove_first_word
from tree_manager import NodeAction

genai.configure(api_key=settings.GOOGLE_API_KEY)


def extract_complete_sentences(text_chunk) -> str:
    """
    Extracts complete sentences from the text buffer, leaving any incomplete
    sentence in the buffer.

    Returns:
        str: The extracted complete sentences.
    """
    # Use re.finditer to get match objects with positions
    matches = list(re.finditer(r"\w([.!?])(?:\s|$)", text_chunk))

    if matches:
        # Get the end index of the last complete sentence
        last_sentence_end_index = matches[-1].end(1)
        # Extract up to this index
        return text_chunk[:last_sentence_end_index]
    else:
        return ""  # No complete sentence found

    # simpler/faster version:
    # last_sentence_end = re.search(r"[.!?][\s\n]*$", self.text_buffer)
    # text_to_process = ""
    # if last_sentence_end:
    #     text_to_process = self.text_buffer[:last_sentence_end.end()]

    # return text_to_process


class ContextualTreeManager:
    def __init__(self, decision_tree: DecisionTree):
        self.decision_tree: DecisionTree = decision_tree
        self.text_buffer: str = ""
        self.transcript_history: str = ""
        self.transcript_history_up_until_curr = ""
        self.future_lookahead_history = ""
        self.text_buffer_size_threshold: int = settings.TEXT_BUFFER_SIZE_THRESHOLD
        self.nodes_to_update: Set[int] = set()
        self.summarizer = Summarizer()
        self.decider = Decider()
        self.rewriter = Rewriter()

    async def process_voice_input(self, transcribed_text: str):
        """
        Processes incoming transcribed text, appends to buffers,
        and triggers text chunk processing when the buffer reaches
        the threshold. Only processes complete sentences.

        Args:
            transcribed_text (str): The transcribed text from the
                                   speech recognition engine.
        """
        self.text_buffer += transcribed_text + " "
        self.transcript_history += transcribed_text + " "

        # Extract complete sentences from the text buffer
        text_to_process = extract_complete_sentences(self.text_buffer)

        # Update the transcript history to maintain a window of relevant context
        self.transcript_history = self.transcript_history[
                                  -self.text_buffer_size_threshold * (settings.TRANSCRIPT_HISTORY_MULTIPLIER + 1):]

        # Determine the point at which to split text for lookahead
        length_of_last_dot = text_to_process[:-1].rfind('.') + 1
        length_of_last_q = text_to_process[:-1].rfind('?') + 1
        length_of_last_exc = text_to_process[:-1].rfind('!') + 1
        # todo just use a regex
        length_of_last_sentence = max(length_of_last_q, length_of_last_exc, length_of_last_dot)

        # The portion before the split point is the main text to process
        text_to_process = text_to_process[:length_of_last_sentence]

        # The portion after the split point is the future lookahead context
        self.future_lookahead_history = self.text_buffer[len(text_to_process):]

        # Update the transcript history up until the current point (excluding lookahead)
        self.transcript_history_up_until_curr = remove_first_word(self.transcript_history)[:-len(self.text_buffer)]

        logging.info(f"Text buffer size is now {len(self.text_buffer)} characters")
        logging.info(f"Text to process size is now {len(text_to_process)} characters")
        logging.info(f"Future lookahead size is now {len(self.future_lookahead_history)} characters")

        if len(text_to_process) > self.text_buffer_size_threshold:
            # if(get_num_req_last_min >= 15):
            #     return
            # num_req_last_min += 2 (no put this in the actual llm call)

            await self._process_text_chunk(text_to_process, self.transcript_history_up_until_curr)
            self.text_buffer = self.text_buffer[len(text_to_process):]  # Clear processed text

            # processed text doesn't include whitespace, so after clearing it may contain just whitespace
            if len(self.text_buffer) < 2:
                self.text_buffer = self.text_buffer.strip()
                # todo: this is a hacky way handle edge case of where there is leftover in text_Buffer, now not ending on a space

    async def _process_text_chunk(self, text_chunk: str, transcript_history_context: str):
        """
        Processes a text chunk, summarizes and analyzes it using LLMs,
        and updates the decision tree accordingly.

        Args:
            text_chunk (str): The chunk of text to process.
            transcript_history_context (str): The relevant portion of the
                                            transcript history for context.
        """

        # Call decide_tree_action with the previous chunk and output for context
        actions = await self.decider.decide_tree_action(
            self.decision_tree, text_chunk, transcript_history_context, self.future_lookahead_history
        )

        # Process each action returned by the decider
        for node_action in actions:
            node_action: NodeAction
            if not node_action.is_complete:
                continue  # todo have seperate buffer for incomplete nodes
            if node_action.action == "CREATE":
                parent_node_id = self.decision_tree.get_node_id_from_name(node_action.neighbour_concept_name)
                new_node_id: int = self.decision_tree.create_new_node(
                    name=node_action.concept_name,
                    parent_node_id=parent_node_id,
                    content=node_action.markdown_content_to_append,
                    summary=node_action.updated_summary_of_node,
                    relationship_to_parent=node_action.relationship_to_neighbour
                )
                self.nodes_to_update.add(new_node_id)

            elif node_action.action == "APPEND":
                chosen_node_id = self.decision_tree.get_node_id_from_name(node_action.concept_name)
                await self._append_to_node(chosen_node_id, node_action.markdown_content_to_append,
                                           node_action.updated_summary_of_node, node_action.labelled_text)

                self.nodes_to_update.add(chosen_node_id)

            else:
                print("Warning: Unexpected mode returned from decide_tree_action")

            # Add the chosen node ID to the list of nodes to update


    async def _append_to_node(self, chosen_node_id, content, summary, text_chunk):
        self.decision_tree.tree[chosen_node_id].append_content(content, summary, text_chunk)

        # only do this every nth time, because append is fine for a couple times before it gets messy
        if self.decision_tree.tree[chosen_node_id].num_appends % settings.BACKGROUND_REWRITE_EVERY_N_APPEND == 0:
            asyncio.create_task(
                self.rewriter.rewrite_node_in_background(self.decision_tree, chosen_node_id)).add_done_callback(
                lambda res: self.nodes_to_update.add(chosen_node_id))
