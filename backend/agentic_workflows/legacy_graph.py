"""
Graph definition for VoiceTree LangGraph workflow
Defines the flow between processing stages
"""

from typing import Dict, Any

try:
    from langgraph.graph import StateGraph, END
    from backend.agentic_workflows.state import VoiceTreeState
    from backend.agentic_workflows.legacy_nodes import (
        segmentation_node,
        relationship_analysis_node, 
        integration_decision_node,
        node_extraction_node
    )
    LANGGRAPH_AVAILABLE = True
except ImportError as e:
    print(f"❌ LangGraph import failed: {e}")
    print("❌ System cannot function without LangGraph - no mock fallback")
    LANGGRAPH_AVAILABLE = False
    raise RuntimeError(f"LangGraph dependencies missing: {e}. Please ensure all dependencies are installed.")


# Stage transition mapping
STAGE_TRANSITIONS = {
    "segmentation_complete": "relationship_analysis",
    "relationship_analysis_complete": "integration_decision",
    "integration_decision_complete": "node_extraction",
    "complete": END,
    "error": END
}


def should_continue(state: Dict[str, Any]) -> str:
    """
    Conditional edge function to determine next step based on current stage
    
    Args:
        state: Current pipeline state
        
    Returns:
        Name of next node or END
    """
    current_stage = state.get("current_stage", "")
    return STAGE_TRANSITIONS.get(current_stage, "segmentation")


def create_voicetree_graph():
    """
    Create and configure the VoiceTree processing graph
    
    Returns:
        Configured StateGraph instance
    """
    if not LANGGRAPH_AVAILABLE:
        return StateGraph(dict)
    
    # Create the state graph
    workflow = StateGraph(VoiceTreeState)
    
    # Define pipeline stages
    stages = [
        ("segmentation", segmentation_node),
        ("relationship_analysis", relationship_analysis_node),
        ("integration_decision", integration_decision_node),
        ("node_extraction", node_extraction_node)
    ]
    
    # Add all nodes
    for stage_name, stage_func in stages:
        workflow.add_node(stage_name, stage_func)
    
    # Set the entry point
    workflow.set_entry_point("segmentation")
    
    # Add conditional edges for each stage
    for i, (stage_name, _) in enumerate(stages):
        # Determine possible next stages
        if i < len(stages) - 1:
            next_stage = stages[i + 1][0]
            edge_mapping = {
                next_stage: next_stage,
                END: END
            }
        else:
            # Last stage only goes to END
            edge_mapping = {END: END}
        
        workflow.add_conditional_edges(
            stage_name,
            should_continue,
            edge_mapping
        )
    
    return workflow


def compile_voicetree_graph():
    """
    Compile the VoiceTree graph for execution
    
    Returns:
        Compiled graph ready for execution
    """
    workflow = create_voicetree_graph()
    return workflow.compile() 