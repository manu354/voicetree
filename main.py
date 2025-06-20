import asyncio
import unittest

from backend.text_to_graph_pipeline.chunk_processing_pipeline.chunk_processor import ChunkProcessor
from backend.text_to_graph_pipeline.tree_manager.decision_tree_ds import DecisionTree
from backend.text_to_graph_pipeline.tree_manager.tree_to_markdown import TreeToMarkdownConverter
from backend.text_to_graph_pipeline.voice_to_text.voice_to_text import VoiceToTextEngine

decision_tree = DecisionTree()
converter = TreeToMarkdownConverter(decision_tree.tree)
processor = ChunkProcessor(decision_tree, 
                          converter=converter, 
                          workflow_state_file="voicetree_workflow_state.json")

async def main():
    voice_engine = VoiceToTextEngine()
    voice_engine.start_listening()
    while True:
        transcription = voice_engine.process_audio_queue()
        if transcription:
            await processor.process_and_convert(transcription)
        await asyncio.sleep(0.01)  # Small delay to prevent CPU spinning


if __name__ == "__main__":
    unit_tests = unittest.TestLoader().discover('backend/tests/unit_tests')
    unit_tests_results = unittest.TextTestRunner().run(unit_tests)
    #
    # integration_tests = unittest.TestLoader().discover('tests/integration_tests/mocked')
    # integration_tests_results = unittest.TextTestRunner().run(integration_tests)

    # if not unit_tests_results.wasSuccessful() or not integration_tests_results:
    #     sys.exit("Unit tests failed. Exiting.")
    asyncio.run(main())
