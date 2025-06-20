import asyncio
import unittest
import os
import shutil
from unittest.mock import patch

from backend.text_to_graph_pipeline.tree_manager import NodeAction
from backend.text_to_graph_pipeline.chunk_processing_pipeline.chunk_processor import ChunkProcessor
from backend.text_to_graph_pipeline.tree_manager.decision_tree_ds import DecisionTree
from backend.text_to_graph_pipeline.tree_manager.tree_to_markdown import TreeToMarkdownConverter
from backend.text_to_graph_pipeline.chunk_processing_pipeline.workflow_adapter import WorkflowResult


class TestIntegrationMockedLLM(unittest.TestCase):
    def setUp(self):
        # Reset the tree and other objects before each test

        self.decision_tree = DecisionTree()
        self.output_dir = "/Users/bobbobby/repos/VoiceTreePoc/test_output"
        self.converter = TreeToMarkdownConverter(self.decision_tree.tree)
        self.processor = ChunkProcessor(self.decision_tree,
                                       converter=self.converter,
                                       output_dir=self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        log_file_path = "voicetree.log"  # todo change this from default, make it a test.log
        if os.path.exists(log_file_path):
            with open(log_file_path, 'w') as f:
                f.truncate()

    def tearDown(self):
        shutil.rmtree(self.output_dir, ignore_errors=True)

    summaries = [
        "## Project Planning Node\n\n- Define project scope.\n- Identify key stakeholders.",
        "## Next Steps for Project\n\n- Need to reach out to investors for advice.\n- Will start with Austin's dad.",
        "## Preparing for Investor Outreach\n\n- Polish Proof of Concept (POC):\n    - Refine user interface.\n    - "
        "Improve summarization quality.\n    - Ensure application robustness and ease of use.\n- Prepare pitch deck "
        "and presentation."
    ]

    @patch('backend.text_to_graph_pipeline.chunk_processing_pipeline.workflow_adapter.WorkflowAdapter.process_transcript')
    async def test_complex_tree_creation_workflow(self, mock_process_transcript):
        """Test complex tree creation using the new workflow system"""
        
        # Mock workflow responses for each transcript processing
        mock_process_transcript.side_effect = [
            # First transcript response
            WorkflowResult(
                success=True,
                new_nodes=["Project Planning"],
                node_actions=[NodeAction(
                    labelled_text="This is a test of the VoiceTree application. I want to create a new node about project planning.",
                    action="CREATE",
                    concept_name="Project Planning",
                    neighbour_concept_name="Root",
                    relationship_to_neighbour="child of",
                    updated_summary_of_node=self.summaries[0],
                    markdown_content_to_append=self.summaries[0],
                    is_complete=True
                )],
                metadata={"chunks_processed": 1}
            ),
            # Second transcript response
            WorkflowResult(
                success=True,
                new_nodes=["Investor Outreach"],
                node_actions=[NodeAction(
                    labelled_text="Another thing I will have to do is start reaching out to investors",
                    action="CREATE", 
                    concept_name="Investor Outreach",
                    neighbour_concept_name="Project Planning",
                    relationship_to_neighbour="child of",
                    updated_summary_of_node=self.summaries[1],
                    markdown_content_to_append=self.summaries[1],
                    is_complete=True
                )],
                metadata={"chunks_processed": 1}
            ),
            # Third transcript response
            WorkflowResult(
                success=True,
                new_nodes=["POC Polish"],
                node_actions=[NodeAction(
                    labelled_text="To be able to start reaching out to investors, I will first have to polish my POC",
                    action="CREATE",
                    concept_name="POC Polish",
                    neighbour_concept_name="Investor Outreach", 
                    relationship_to_neighbour="child of",
                    updated_summary_of_node=self.summaries[2],
                    markdown_content_to_append=self.summaries[2],
                    is_complete=True
                )],
                metadata={"chunks_processed": 1}
            )
        ]
        
        # Test transcripts
        transcript1 = """
         This is a test of the VoiceTree application.
         I want to create a new node about project planning. 
         The first step is to define the project scope. 
         The next step is to identify the key stakeholders.
         """

        transcript2 = (
            "Another thing I will have to do is start reaching out to investors "
            "to see what next steps they would recommend for me. "
            "I should talk to Austin's dad first."
        )

        transcript3 = (
            "To be able to start reaching out to investors, I will first have to polish my POC. "
            "This involves refining the user interface, improving the summarization quality, "
            "and making sure the application is robust and easy to use. "
            "I'll also need to prepare a compelling pitch deck and presentation."
        )

        # Process the transcripts
        await self.processor.process_and_convert(transcript1)
        await self.processor.process_and_convert(transcript2)
        await self.processor.process_and_convert(transcript3)
        
        # Assertions
        tree = self.decision_tree.tree

        # 1. Check the Number of Nodes (should be 4)
        self.assertEqual(len(tree), 4, "The tree should have 4 nodes.")

        # 2. Verify Node Content Using Keywords
        project_planning_node_id = self.assert_node_content_contains(tree, ["project", "planning"])
        investors_node_id = self.assert_node_content_contains(tree, ["investors", "austin"])
        poc_node_id = self.assert_node_content_contains(tree, ["poc"])

        # 3.  Check Parent-Child Relationships
        root_node_children = tree[0].children
        self.assertIn(project_planning_node_id, root_node_children,
                      "Node 'project planning' should be a child of the root node.")
        self.assertIn(investors_node_id, tree[project_planning_node_id].children,
                      "Node 'investors' should be a child of 'project planning'.")
        self.assertIn(poc_node_id, tree[investors_node_id].children,
                      "Node 'polish my POC' should be a child of 'investors'.")

        # 4. Verify Markdown File Creation and Links
        for node_id, node_data in tree.items():
            file_path = os.path.join(self.output_dir, node_data.filename)
            self.assertTrue(os.path.exists(file_path), f"Markdown file for Node {node_id} not found.")

            with open(file_path, "r") as f:
                content = f.read().lower()  # Convert content to lowercase
                # a Check for parent link
                parent_id = self.tree_manager.decision_tree.get_parent_id(node_id)
                if parent_id is not None:
                    parent_filename = tree[parent_id].filename
                    self.assertIn(f"- child of [[{parent_filename}]]".lower(), content,
                                  # Convert expected link to lowercase
                                  f"Missing child link to parent in Node {node_id} Markdown file.")
                for keyword in self.get_keywords_for_node(node_id):
                    self.assertIn(keyword.lower(), content,
                                  f"Keyword '{keyword}' not found in Node {node_id} Markdown file.")

    # Update the test method names and remove the old patches
    def test_complex_tree_creation(self):
        """Test complex tree creation using workflow system"""
        asyncio.run(self.test_complex_tree_creation_workflow())

    @patch('backend.text_to_graph_pipeline.chunk_processing_pipeline.workflow_adapter.WorkflowAdapter.process_transcript')
    async def test_complex_tree_creation_append_mode_workflow(self, mock_process_transcript):
        """Test complex tree creation with APPEND mode using the new workflow system"""
        
        # Mock workflow responses showing APPEND behavior
        mock_process_transcript.side_effect = [
            # First transcript response
            WorkflowResult(
                success=True,
                new_nodes=["Project Planning"],
                node_actions=[NodeAction(
                    labelled_text="This is a test of the VoiceTree application. I want to create a new node about project planning.",
                    action="CREATE",
                    concept_name="Project Planning",
                    neighbour_concept_name="Root",
                    relationship_to_neighbour="child of",
                    updated_summary_of_node=self.summaries[0],
                    markdown_content_to_append=self.summaries[0],
                    is_complete=True
                )],
                metadata={"chunks_processed": 1}
            ),
            # Second transcript response - APPEND to existing node
            WorkflowResult(
                success=True,
                new_nodes=[],  # No new nodes created, just appending
                node_actions=[NodeAction(
                    labelled_text="Another thing I will have to do is start reaching out to investors",
                    action="APPEND",
                    concept_name="Project Planning",
                    neighbour_concept_name="Project Planning",
                    relationship_to_neighbour="append to",
                    updated_summary_of_node=self.summaries[1],
                    markdown_content_to_append=self.summaries[1],
                    is_complete=True
                )],
                metadata={"chunks_processed": 1}
            ),
            # Third transcript response - CREATE new node
            WorkflowResult(
                success=True,
                new_nodes=["POC Polish"],
                node_actions=[NodeAction(
                    labelled_text="To be able to start reaching out to investors, I will first have to polish my POC",
                    action="CREATE",
                    concept_name="POC Polish",
                    neighbour_concept_name="Project Planning",
                    relationship_to_neighbour="child of",
                    updated_summary_of_node=self.summaries[2],
                    markdown_content_to_append=self.summaries[2],
                    is_complete=True
                )],
                metadata={"chunks_processed": 1}
            )
        ]
        
        # Test transcripts
        transcript1 = """
         This is a test of the VoiceTree application.
         I want to create a new node about project planning. 
         The first step is to define the project scope. 
         The next step is to identify the key stakeholders.
         """

        transcript2 = (
            "Another thing I will have to do is start reaching out to investors "
            "to see what next steps they would recommend for me. "
            "I should talk to Austin's dad first."
        )

        transcript3 = (
            "To be able to start reaching out to investors, I will first have to polish my POC. "
            "This involves refining the user interface, improving the summarization quality, "
            "and making sure the application is robust and easy to use. "
            "I'll also need to prepare a compelling pitch deck and presentation."
        )

        # Process the transcripts
        await self.processor.process_and_convert(transcript1)
        await self.processor.process_and_convert(transcript2)
        await self.processor.process_and_convert(transcript3)
        
        # Assertions
        tree = self.decision_tree.tree

        # 1. Check the Number of Nodes (should be 3 due to APPEND behavior)
        self.assertEqual(len(tree), 3, "The tree should have 3 nodes (due to APPEND).")

        # 2. Verify Node Content Using Keywords
        project_planning_node_id = self.assert_node_content_contains(tree, ["project", "planning"]) 
        investors_node_id = self.assert_node_content_contains(tree, ["investors", "austin"])
        poc_node_id = self.assert_node_content_contains(tree, ["poc"])

        # Since we are appending, investor_node_id should be the same as project planning node id
        self.assertEqual(investors_node_id, project_planning_node_id)

        # 3.  Check Parent-Child Relationship
        root_node_children = tree[0].children
        self.assertIn(project_planning_node_id, root_node_children,
                      "Node 'project planning' should be a child of the root node.")
        self.assertIn(poc_node_id, tree[investors_node_id].children,
                      "Node 'polish my POC' should be a child of 'investors'.")

        # 4. Verify Markdown File Creation and Links
        for node_id, node_data in tree.items():
            file_path = os.path.join(self.output_dir, node_data.filename)
            self.assertTrue(os.path.exists(file_path), f"Markdown file for Node {node_id} not found.")

            with open(file_path, "r") as f:
                content = f.read().lower()  # Convert content to lowercase
                # a Check for parent link
                parent_id = self.tree_manager.decision_tree.get_parent_id(node_id)
                if parent_id is not None:
                    parent_filename = tree[parent_id].filename
                    self.assertIn(f"- child of [[{parent_filename}]]".lower(), content,
                                  # Convert expected link to lowercase
                                  f"Missing child link to parent in Node {node_id} Markdown file.")
                for keyword in self.get_keywords_for_node(node_id):
                    self.assertIn(keyword.lower(), content,
                                  f"Keyword '{keyword}' not found in Node {node_id} Markdown file.")

    def test_complex_tree_creation_append_mode(self):
        """Test complex tree creation with APPEND mode using workflow system"""
        asyncio.run(self.test_complex_tree_creation_append_mode_workflow())

    # ... (Your helper functions) ...
    # Helper functions to make assertions more readable and reusable
    def assert_node_content_contains(self, tree, keywords):
        """Asserts that a node with the given keywords exists in the tree."""
        node_id = self.find_node_id_by_keywords(tree, keywords)
        self.assertIsNotNone(node_id, f"Node with content containing '{keywords}' not found.")
        return node_id

    def find_node_id_by_keywords(self, tree, keywords):
        """Finds the node ID based on the presence of all given keywords in the content."""
        for node_id, node_data in tree.items():
            if all(keyword.lower() in node_data.content.lower() for keyword in keywords):
                return node_id
        return None

    def get_keywords_for_node(self, node_id):
        """Returns a list of keywords to check for in the Markdown file content."""
        if node_id == 0:
            return ["today"]  # Keywords for the root node
        elif node_id == 1:
            return ["project", "planning"]
        elif node_id == 2:
            return ["investor"]
        elif node_id == 3:
            return ["poc"]
        else:
            return []  # No specific keywords for other nodes

    def print_tree(self, tree, node_id=0, indent=0):
        """Prints a simple text-based representation of the tree."""
        node_data = tree[node_id]
        print("  " * indent + f"- {node_data.content}")
        for child_id in node_data.children:
            self.print_tree(tree, child_id, indent + 1)
