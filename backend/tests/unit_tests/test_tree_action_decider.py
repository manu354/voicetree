"""
Unit tests for TreeActionDeciderWorkflow.

These tests use mocks to verify orchestration logic without running actual LLMs.
Tests focus on high-level behavior:
1. Correct agent orchestration order
2. Tree state changes after workflow execution
3. Edge case handling
4. Orphan node merging
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Set

# Import models first (these should exist)
from backend.text_to_graph_pipeline.agentic_workflows.models import (
    AppendAction, 
    CreateAction, 
    UpdateAction,
    BaseTreeAction,
    AppendAgentResult,
    SegmentModel
)
from backend.text_to_graph_pipeline.tree_manager.decision_tree_ds import DecisionTree, Node
from backend.text_to_graph_pipeline.chunk_processing_pipeline.tree_action_decider_workflow import TreeActionDeciderWorkflow


def create_mock_append_result(actions):
    """Helper to create AppendAgentResult from a list of actions"""
    # Create segments for each action
    segments = []
    texts = []
    for action in actions:
        if hasattr(action, 'content'):
            text = action.content
        else:
            text = "Test content"
        segments.append(SegmentModel(reasoning="Test", text=text, is_complete=True))
        texts.append(text)
    
    return AppendAgentResult(
        actions=actions,
        segments=segments,
        completed_text=" ".join(texts)
    )


class TestTreeActionDeciderWorkflow:
    """Unit tests for TreeActionDeciderWorkflow orchestration logic"""
    
    @pytest.fixture
    def mock_append_agent(self):
        """Mock AppendToRelevantNodeAgent"""
        agent = Mock()
        agent.run = AsyncMock()
        return agent
    
    @pytest.fixture
    def mock_optimizer_agent(self):
        """Mock SingleAbstractionOptimizerAgent"""
        agent = Mock()
        agent.run = AsyncMock()
        return agent
    
    @pytest.fixture
    def mock_tree_applier(self):
        """Mock TreeActionApplier"""
        applier = Mock()
        applier.apply = Mock()
        return applier
    
    @pytest.fixture
    def simple_tree(self):
        """Create a simple tree for testing"""
        tree = DecisionTree()
        node = Node(
            name="Test Node",
            node_id=1,
            content="Test content",
            summary="Test summary"
        )
        tree.tree[1] = node
        return tree
    
    @pytest.fixture
    def workflow(self, mock_append_agent, mock_optimizer_agent):
        """Create TreeActionDeciderWorkflow with mocked dependencies"""
        workflow = TreeActionDeciderWorkflow()
        workflow.append_agent = mock_append_agent
        workflow.optimizer_agent = mock_optimizer_agent
        return workflow
    
    @pytest.mark.asyncio
    async def test_workflow_calls_agents_in_correct_order(
        self, workflow, mock_append_agent, mock_optimizer_agent, 
        mock_tree_applier, simple_tree
    ):
        """Test Case 1: Verify two-step pipeline execution order"""
        # Given: Mock agents that return predictable actions
        placement_actions = [
            AppendAction(action="APPEND", target_node_id=1, content="New content"),
            CreateAction(
                action="CREATE",
                parent_node_id=1, 
                new_node_name="New Node", 
                content="Content",
                summary="New node summary",
                relationship="subtask of"
            )
        ]
        
        # Create mock segments
        segments = [
            SegmentModel(reasoning="Complete segment", text="New content", is_complete=True),
            SegmentModel(reasoning="Complete segment", text="Content", is_complete=True)
        ]
        
        # Mock append agent to return AppendAgentResult
        mock_append_agent.run.return_value = AppendAgentResult(
            actions=placement_actions,
            segments=segments,
            completed_text="New content Content"
        )
        
        # Mock TreeActionApplier to return modified nodes
        mock_tree_applier.apply.return_value = {1, 99}  # nodes 1 and 99 were modified
        
        # Mock optimizer to return optimization actions
        optimization_actions = [
            UpdateAction(action="UPDATE", node_id=1, new_content="Optimized content", new_summary="New summary")
        ]
        mock_optimizer_agent.run.return_value = optimization_actions
        
        # Patch TreeActionApplier
        with patch('backend.text_to_graph_pipeline.chunk_processing_pipeline.tree_action_decider_workflow.TreeActionApplier') as mock_applier_class:
            mock_applier_class.return_value = mock_tree_applier
            
            # When: Run workflow
            result = await workflow.run(
                transcript_text="Test transcript",
                decision_tree=simple_tree,
                transcript_history=""
            )
        
        # Then: Verify call order
        # 1. AppendAgent called first
        mock_append_agent.run.assert_called_once_with(
            transcript_text="Test transcript",
            decision_tree=simple_tree,
            transcript_history=""
        )
        
        # 2. TreeActionApplier called with placement actions
        mock_tree_applier.apply.assert_called()
        
        # 3. OptimizerAgent called for each modified node
        assert mock_optimizer_agent.run.call_count == 2  # Called for nodes 1 and 99
        
        # 4. Workflow returns optimization actions
        assert len(result) == 2  # One optimization action per modified node
        assert all(isinstance(action, UpdateAction) for action in result)
    
    @pytest.mark.asyncio
    async def test_workflow_applies_actions_immediately(
        self, workflow, mock_append_agent, mock_optimizer_agent,
        mock_tree_applier, simple_tree
    ):
        """Test Case 2: Actions are applied immediately, not returned"""
        # Given: AppendAgent returns placement actions
        placement_actions = [
            AppendAction(action="APPEND", target_node_id=1, content="Append this"),
            CreateAction(
                action="CREATE",
                parent_node_id=1, 
                new_node_name="New Node", 
                content="Create this",
                summary="New node summary",
                relationship="related to"
            )
        ]
        mock_append_agent.run.return_value = create_mock_append_result(placement_actions)
        
        # Mock applier and optimizer
        mock_tree_applier.apply.return_value = {1}
        mock_optimizer_agent.run.return_value = [
            UpdateAction(action="UPDATE", node_id=1, new_content="Optimized", new_summary="Summary")
        ]
        
        with patch('backend.text_to_graph_pipeline.chunk_processing_pipeline.tree_action_decider_workflow.TreeActionApplier') as mock_applier_class:
            mock_applier_class.return_value = mock_tree_applier
            
            # When: Run workflow
            result = await workflow.run(
                transcript_text="Test",
                decision_tree=simple_tree
            )
        
        # Then: 
        # 1. TreeActionApplier called twice (placement + optimization)
        assert mock_tree_applier.apply.call_count == 2
        
        # 2. First call was with placement actions
        first_call_actions = mock_tree_applier.apply.call_args_list[0][0][0]
        assert len(first_call_actions) == 2
        
        # 3. Second call was with optimization actions
        second_call_actions = mock_tree_applier.apply.call_args_list[1][0][0]
        assert len(second_call_actions) == 1
        
        # 4. Workflow returns optimization actions
        assert len(result) == 1  # One optimization action
        assert isinstance(result[0], UpdateAction)
    
    @pytest.mark.asyncio
    async def test_tracks_modified_nodes_from_placement(
        self, workflow, mock_append_agent, mock_optimizer_agent,
        mock_tree_applier, simple_tree
    ):
        """Test Case 3: Workflow tracks which nodes were modified"""
        # Given: Placement actions that modify specific nodes
        placement_actions = [
            AppendAction(action="APPEND", target_node_id=1, content="Content 1"),
            AppendAction(action="APPEND", target_node_id=3, content="Content 3"),
            CreateAction(
                action="CREATE",
                parent_node_id=2, 
                new_node_name="New", 
                content="Content",
                summary="New node summary",
                relationship="child of"
            )
        ]
        mock_append_agent.run.return_value = create_mock_append_result(placement_actions)
        
        # TreeActionApplier reports nodes 1, 3, and 5 were modified
        modified_nodes = {1, 3, 5}
        mock_tree_applier.apply.return_value = modified_nodes
        
        # Mock optimizer responses
        mock_optimizer_agent.run.return_value = []
        
        with patch('backend.text_to_graph_pipeline.chunk_processing_pipeline.tree_action_decider_workflow.TreeActionApplier') as mock_applier_class:
            mock_applier_class.return_value = mock_tree_applier
            
            # When: Run workflow
            await workflow.run(
                transcript_text="Test",
                decision_tree=simple_tree
            )
        
        # Then: OptimizerAgent called exactly for nodes [1, 3, 5]
        assert mock_optimizer_agent.run.call_count == len(modified_nodes)
        
        # Verify each node was passed to optimizer
        called_node_ids = {
            call.kwargs['node_id'] 
            for call in mock_optimizer_agent.run.call_args_list
        }
        assert called_node_ids == modified_nodes
    
    @pytest.mark.asyncio
    async def test_optimization_actions_applied_per_node(
        self, workflow, mock_append_agent, mock_optimizer_agent,
        mock_tree_applier, simple_tree
    ):
        """Test Case 4: Optimization actions are applied immediately for each node"""
        # Given: 3 modified nodes
        mock_append_agent.run.return_value = create_mock_append_result([
            AppendAction(action="APPEND", target_node_id=1, content="Test")
        ])
        
        # First apply returns modified nodes
        mock_tree_applier.apply.side_effect = [
            {1, 2, 3},  # First call (placement) returns these modified nodes
            {1},        # Second call (optimization for node 1)
            {2},        # Third call (optimization for node 2)
            {3}         # Fourth call (optimization for node 3)
        ]
        
        # Each node produces different optimization actions
        def optimizer_side_effect(node_id, **kwargs):
            if node_id == 1:
                return [
                    UpdateAction(action="UPDATE", node_id=1, new_content="Updated 1", new_summary="Summary 1"),
                    CreateAction(
                        action="CREATE",
                        parent_node_id=1, 
                        new_node_name="Child 1", 
                        content="Content",
                        summary="Child summary",
                        relationship="subtask of"
                    )
                ]
            elif node_id == 2:
                return [
                    UpdateAction(action="UPDATE", node_id=2, new_content="Updated 2", new_summary="Summary 2")
                ]
            else:  # node_id == 3
                return [
                    CreateAction(
                        action="CREATE",
                        parent_node_id=3, 
                        new_node_name="Child 3", 
                        content="Content",
                        summary="Child summary",
                        relationship="subtask of"
                    )
                ]
        
        mock_optimizer_agent.run.side_effect = optimizer_side_effect
        
        with patch('backend.text_to_graph_pipeline.chunk_processing_pipeline.tree_action_decider_workflow.TreeActionApplier') as mock_applier_class:
            mock_applier_class.return_value = mock_tree_applier
            
            # When: Run workflow
            result = await workflow.run(
                transcript_text="Test",
                decision_tree=simple_tree
            )
        
        # Then: 
        # 1. TreeActionApplier called 4 times (1 placement + 3 optimization)
        assert mock_tree_applier.apply.call_count == 4
        
        # 2. Optimizer called 3 times (once per modified node)
        assert mock_optimizer_agent.run.call_count == 3
        
        # 3. Result contains optimization actions  
        assert len(result) == 4  # 2 + 1 + 1 = 4 total optimization actions
        update_count = sum(1 for a in result if isinstance(a, UpdateAction))
        create_count = sum(1 for a in result if isinstance(a, CreateAction))
        assert update_count == 2  # From node 1 and node 2
        assert create_count == 2  # From node 1 and node 3
    
    @pytest.mark.asyncio
    async def test_handles_empty_optimization_response(
        self, workflow, mock_append_agent, mock_optimizer_agent,
        mock_tree_applier, simple_tree
    ):
        """Test Case 5: Gracefully handles when optimizer returns no actions"""
        # Given: Some nodes return empty optimization
        mock_append_agent.run.return_value = create_mock_append_result([
            AppendAction(action="APPEND", target_node_id=1, content="Test")
        ])
        mock_tree_applier.apply.side_effect = [
            {1, 2, 3},  # First call (placement)
            {2}         # Second call (only node 2 had optimization)
        ]
        
        # Mixed responses - some empty, some with actions
        def optimizer_side_effect(node_id, **kwargs):
            if node_id == 1:
                return []  # Empty
            elif node_id == 2:
                return [UpdateAction(action="UPDATE", node_id=2, new_content="Updated", new_summary="Summary")]
            else:
                return []  # Empty
        
        mock_optimizer_agent.run.side_effect = optimizer_side_effect
        
        with patch('backend.text_to_graph_pipeline.chunk_processing_pipeline.tree_action_decider_workflow.TreeActionApplier') as mock_applier_class:
            mock_applier_class.return_value = mock_tree_applier
            
            # When: Run workflow
            result = await workflow.run(
                transcript_text="Test",
                decision_tree=simple_tree
            )
        
        # Then: 
        # 1. Optimizer called 3 times (once per node)
        assert mock_optimizer_agent.run.call_count == 3
        
        # 2. TreeActionApplier called only twice (placement + only node 2's optimization)
        assert mock_tree_applier.apply.call_count == 2
        
        # 3. Result contains only non-empty optimization responses
        assert len(result) == 1  # Only node 2 had optimization actions
        assert isinstance(result[0], UpdateAction)
        assert result[0].node_id == 2
    
    @pytest.mark.asyncio
    async def test_no_placement_actions(
        self, workflow, mock_append_agent, mock_optimizer_agent,
        simple_tree
    ):
        """Test Case 6: Handle when no placement needed"""
        # Given: AppendAgent returns empty list
        mock_append_agent.run.return_value = create_mock_append_result([])
        
        # When: Run workflow
        result = await workflow.run(
            transcript_text="Test",
            decision_tree=simple_tree
        )
        
        # Then: No optimizer calls, empty output
        mock_optimizer_agent.run.assert_not_called()
        assert result == []
    
    @pytest.mark.asyncio
    async def test_placement_creates_new_nodes(
        self, workflow, mock_append_agent, mock_optimizer_agent,
        mock_tree_applier, simple_tree
    ):
        """Test Case 7: New nodes from CreateAction are optimized"""
        # Given: CreateAction creates a new node
        placement_actions = [
            CreateAction(
                action="CREATE",
                parent_node_id=1, 
                new_node_name="New Node", 
                content="Content",
                summary="New node summary",
                relationship="child of"
            )
        ]
        mock_append_agent.run.return_value = create_mock_append_result(placement_actions)
        
        # TreeActionApplier reports new node 99 was created
        mock_tree_applier.apply.side_effect = [
            {99},  # First call (placement) creates node 99
            {99}   # Second call (optimization) modifies node 99
        ]
        
        # Mock optimizer response for new node
        mock_optimizer_agent.run.return_value = [
            UpdateAction(action="UPDATE", node_id=99, new_content="Optimized new node", new_summary="Summary")
        ]
        
        with patch('backend.text_to_graph_pipeline.chunk_processing_pipeline.tree_action_decider_workflow.TreeActionApplier') as mock_applier_class:
            mock_applier_class.return_value = mock_tree_applier
            
            # When: Run workflow
            result = await workflow.run(
                transcript_text="Test",
                decision_tree=simple_tree
            )
        
        # Then: 
        # 1. OptimizerAgent called for new node 99
        assert mock_optimizer_agent.run.call_count == 1
        call_args = mock_optimizer_agent.run.call_args
        assert call_args.kwargs['node_id'] == 99
        
        # 2. TreeActionApplier called twice (placement + optimization)
        assert mock_tree_applier.apply.call_count == 2
        
        # 3. Result contains optimization action for the new node
        assert len(result) == 1
        assert isinstance(result[0], UpdateAction)
        assert result[0].node_id == 99
    
    @pytest.mark.asyncio
    async def test_orphan_nodes_merged_before_optimization(
        self, workflow, mock_append_agent, mock_optimizer_agent,
        mock_tree_applier, simple_tree
    ):
        """Test Case 8: Multiple orphan CREATE actions are merged into one mega node"""
        # Given: Multiple CREATE actions that create orphan nodes (parent_node_id=None)
        placement_actions = [
            AppendAction(action="APPEND", target_node_id=1, content="Regular append"),
            CreateAction(
                action="CREATE",
                parent_node_id=None,  # Orphan node
                new_node_name="First Orphan", 
                content="First orphan content",
                summary="First orphan summary",
                relationship=""  # Empty string for orphan nodes
            ),
            CreateAction(
                action="CREATE",
                parent_node_id=None,  # Another orphan node
                new_node_name="Second Orphan", 
                content="Second orphan content",
                summary="Second orphan summary",
                relationship=""  # Empty string for orphan nodes
            ),
            CreateAction(
                action="CREATE",
                parent_node_id=1,  # Not an orphan - has parent
                new_node_name="Child Node", 
                content="Child content",
                summary="Child summary",
                relationship="subtask of"
            )
        ]
        mock_append_agent.run.return_value = create_mock_append_result(placement_actions)
        
        # Mock applier to return modified nodes
        mock_tree_applier.apply.side_effect = [
            {1, 100, 101},  # First call (placement with merged orphans)
            {1},            # Optimization calls for each node
            {100},
            {101}
        ]
        
        # Mock optimizer returns some optimization actions
        mock_optimizer_agent.run.return_value = [
            UpdateAction(action="UPDATE", node_id=100, new_content="Optimized", new_summary="Summary")
        ]
        
        with patch('backend.text_to_graph_pipeline.chunk_processing_pipeline.tree_action_decider_workflow.TreeActionApplier') as mock_applier_class:
            mock_applier_class.return_value = mock_tree_applier
            
            # When: Run workflow
            result = await workflow.run(
                transcript_text="Test with orphans",
                decision_tree=simple_tree
            )
        
        # Then: TreeActionApplier should receive merged actions (3 total: 1 append, 1 merged orphan, 1 regular create)
        first_apply_call = mock_tree_applier.apply.call_args_list[0]
        applied_actions = first_apply_call[0][0]
        assert len(applied_actions) == 3
        
        # Verify orphan nodes were merged
        orphan_creates = [a for a in applied_actions if isinstance(a, CreateAction) and a.parent_node_id is None]
        assert len(orphan_creates) == 1  # Only one merged orphan
        merged_orphan = orphan_creates[0]
        assert "First Orphan" in merged_orphan.new_node_name
        assert "Second Orphan" in merged_orphan.new_node_name
        assert "First orphan content" in merged_orphan.content
        assert "Second orphan content" in merged_orphan.content
        
        # Optimizer should be called for each modified node
        assert mock_optimizer_agent.run.call_count == 3
        
        # Result should contain optimization actions (one per node)
        assert len(result) == 3  # One optimization action per modified node
        assert all(isinstance(action, UpdateAction) for action in result)