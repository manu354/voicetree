"""
Pydantic models for VoiceTree agentic workflow structured output
"""

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class BaseTreeAction(BaseModel):
    """Base class for all tree actions"""
    action: str = Field(description="Action type")


class SegmentModel(BaseModel):
    """Model for segmentation stage output"""
    reasoning: str = Field(description="Analysis of why this is segmented as a distinct segment and completeness assessment")
    text: str = Field(description="Segment content")
    is_complete: bool = Field(description="Whether this segment representsa complete thought")


class SegmentationResponse(BaseModel):
    """Response model for segmentation stage"""
    segments: List[SegmentModel] = Field(description="List of segments (which together commpletely represent the original chunk)")
    debug_notes: Optional[str] = Field(default=None, description="Your observations about any confusing aspects of the prompt, contradictions you faced, unclear instructions, or any difficulties in completing the task")


class RelationshipAnalysis(BaseModel):
    """Model for relationship analysis stage output"""
    name: str = Field(description="Name of the chunk being analyzed")
    text: str = Field(description="Text content of the chunk")
    reasoning: str = Field(description="Step-by-step analysis for the relationship")
    relevant_node_name: str = Field(description="Name of most relevant existing node or 'NO_RELEVANT_NODE'")
    relationship: Optional[str] = Field(description="Brief relationship description or null")


class RelationshipResponse(BaseModel):
    """Response model for relationship analysis stage"""
    analyzed_chunks: List[RelationshipAnalysis] = Field(description="Analysis results for each chunk")




class NodeSummary(BaseModel):
    """Summary information about a node for neighbor context"""
    id: int = Field(description="Node ID")
    name: str = Field(description="Node name")
    summary: str = Field(description="Node summary")
    relationship: str = Field(description="Relationship to the target node (parent/sibling/child)")


class UpdateAction(BaseTreeAction):
    """Model for UPDATE tree action"""
    action: Literal["UPDATE"] = Field(description="Action type")
    node_id: int = Field(description="ID of node to update")
    new_content: str = Field(description="New content to replace existing content")
    new_summary: str = Field(description="New summary to replace existing summary")


class CreateAction(BaseTreeAction):
    """Model for CREATE action in optimization context"""
    action: Literal["CREATE"] = Field(description="Action type")
    # Legacy name-based field (deprecated)
    target_node_name: Optional[str] = Field(default=None, description="Name of parent node (deprecated, use parent_node_id)")
    # New ID-based field
    parent_node_id: Optional[int] = Field(default=None, description="ID of parent node (-1 for root)")
    new_node_name: str = Field(description="Name for the new node")
    content: str = Field(description="Content for the new node")
    summary: str = Field(description="Summary for the new node")
    relationship: str = Field(description="Relationship to parent (e.g., 'subtask of')")


class AppendAction(BaseTreeAction):
    """Model for APPEND action - adds content to existing node"""
    action: Literal["APPEND"] = Field(description="Action type")
    target_node_id: int = Field(description="ID of node to append content to")
    target_node_name: Optional[str] = Field(default=None, description="Name of target node (for fallback if ID not found)")
    content: str = Field(description="Content to append to the node")


class ChildNodeSpec(BaseModel):
    """Specification for a new child node to be created"""
    name: str = Field(description="Name for the new child node")
    content: str = Field(description="Content for the new child node")
    summary: str = Field(description="Summary for the new child node")
    relationship: str = Field(description="Relationship to parent (e.g., 'subtask of', 'implements', 'solves')")
    
    class Config:
        extra = "forbid"  # This makes Pydantic reject any extra fields!


class OptimizationResponse(BaseModel):
    """Response model for single abstraction optimization - no union types"""
    reasoning: str = Field(description="Analysis of the node and optimization decision")
    
    # Original node update (if needed)
    update_original: bool = Field(description="Whether to update the original node")
    original_new_content: Optional[str] = Field(default=None, description="New content for original node (if update_original=True)")
    original_new_summary: Optional[str] = Field(default=None, description="New summary for original node (if update_original=True)")
    
    # New child nodes to create (can be empty list)
    create_child_nodes: List[ChildNodeSpec] = Field(
        default_factory=list,
        description="List of child nodes to create (empty if no split needed)"
    )
    
    debug_notes: Optional[str] = Field(default=None, description="Your observations about any confusing aspects of the prompt, contradictions you faced, unclear instructions, or any difficulties in completing the task")


class TargetNodeIdentification(BaseModel):
    """Model for identifying target node for a segment"""
    text: str = Field(description="Text content of the segment")
    reasoning: str = Field(description="Analysis for choosing the target node")
    target_node_id: int = Field(description="ID of target node (use -1 for new nodes)")
    target_node_name: Optional[str] = Field(default=None, description="Name of the chosen existing node (required when is_new_node=False)")
    is_new_node: bool = Field(description="Whether this is a new node to be created")
    new_node_name: Optional[str] = Field(default=None, description="Name for new node (required if is_new_node=True)")
    
    def model_post_init(self, __context):
        """Validate that new nodes have names and existing nodes have valid IDs"""
        if self.is_new_node:
            if self.target_node_id != -1:
                raise ValueError("New nodes must have target_node_id=-1")
            if not self.new_node_name:
                raise ValueError("new_node_name is required when is_new_node=True")
            if self.target_node_name is not None:
                raise ValueError("target_node_name must be null when is_new_node=True")
        else:
            if self.target_node_id < 0:
                raise ValueError("Existing nodes must have non-negative target_node_id (0 or greater)")
            if not self.target_node_name:
                raise ValueError("target_node_name is required when is_new_node=False")


class TargetNodeResponse(BaseModel):
    """Response model for identify target node stage"""
    target_nodes: List[TargetNodeIdentification] = Field(description="Target node for each segment")
    debug_notes: Optional[str] = Field(default=None, description="Your observations about any confusing aspects of the prompt, contradictions you faced, unclear instructions, or any difficulties in completing the task")


from typing import Union
class AppendAgentResult(BaseModel):
    """Result from AppendToRelevantNodeAgent containing actions and segment info"""
    actions: List[Union[AppendAction, CreateAction]] = Field(description="List of actions to apply")
    segments: List[SegmentModel] = Field(description="List of segments with completeness info")
    completed_text: str = Field(description="Concatenated text of all complete segments that should be flushed")

