# treeToMarkdown.py
import logging
import os
import re
import traceback
from typing import Dict, TYPE_CHECKING

from backend.text_to_graph_pipeline.tree_manager.utils import deduplicate_content, insert_yaml_frontmatter

if TYPE_CHECKING:
    from backend.text_to_graph_pipeline.tree_manager.decision_tree_ds import Node


def generate_filename_from_keywords(node_title, max_keywords=3):
    # note, could also do this with rake keyword extraction
    file_name = node_title
    file_name = re.sub(r'summary\s*:', '', file_name, flags=re.IGNORECASE)  # Remove "summary:"
    file_name = re.sub(r'#+\s*title\s*:', '', file_name, flags=re.IGNORECASE)  # Remove "## title"
    
    # Allow only letters, numbers, hyphens, and underscores
    # Replace all other characters with underscores
    file_name = re.sub(r'[^a-zA-Z0-9_-]', '_', file_name)
    
    # Replace multiple consecutive underscores with a single underscore
    file_name = re.sub(r'_+', '_', file_name)
    
    # Remove leading and trailing underscores
    file_name = file_name.strip('_')
    
    # Ensure filename is not empty
    if not file_name:
        file_name = "untitled"

    return file_name + ".md"


def slugify(text):
    """Converts text to a valid filename."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    text = text.strip('_')
    return text


class TreeToMarkdownConverter:
    def __init__(self, tree_data: Dict[int, 'Node']):
        # self.mContextualTreeManager = contextual_tree_manager
        self.tree_data = tree_data

    def convert_nodes(self, output_dir="markdownTreeVaultDefault", nodes_to_update=None):
        """Converts the specified nodes to Markdown files."""

        os.makedirs(output_dir, exist_ok=True)
        if (len(nodes_to_update)> 0):
            logging.info(f"updating/writing markdown for nodes {nodes_to_update}")

        if nodes_to_update:
            for node_id in nodes_to_update:
                self.convert_node(node_id, output_dir)

    def convert_node(self, node_id, output_dir):
        try:
            node_data = self.tree_data[node_id]
            if node_data.filename:
                file_name = node_data.filename
            else:
                file_name = generate_filename_from_keywords(node_data.content)
                node_data.filename = file_name  # Store the filename
                # title_match = re.search(r'^##+(.*)', node_data.content, re.MULTILINE)
                # node_data.content.replace(title_match.group(0), "")
            file_path = os.path.join(output_dir, file_name)

            with open(file_path, 'w') as f:
                # Write YAML frontmatter
                frontmatter = insert_yaml_frontmatter({
                    "title": node_data.title,
                    "node_id": node_id,
                    "created_at": node_data.created_at.isoformat(),
                    "modified_at": node_data.modified_at.isoformat()
                })
                f.write(frontmatter)

                if not node_data.content or "###" not in node_data.content:
                    f.write(f"### {node_data.summary}\n\n")

                # Deduplicate content before writing to improve quality
                clean_content = deduplicate_content(node_data.content)
                f.write(f"{clean_content}\n\n\n-----------------\n_Links:_\n")

                # Add child links
                if node_data.children:
                    f.write(f"Children:\n")
                for child_id in node_data.children:
                    child_node = self.tree_data.get(child_id)
                    if child_node:
                        if not child_node.filename:
                            logging.warning(f"Child node {child_id} missing filename")
                            continue
                        child_file_name = child_node.filename
                        # Get the relationship from child's perspective
                        child_relationship = "child of"
                        if child_id in self.tree_data and node_id in self.tree_data[child_id].relationships:
                            child_relationship = self.tree_data[child_id].relationships[node_id]
                            child_relationship = self.convert_to_snake_case(child_relationship)
                        f.write(f"- [[{child_file_name}]] {child_relationship} (this node)\n")
                    else:
                        logging.error(f"Child node {child_id} not found in tree_data")

                # add parent links
                parent_id = self.get_parent_id(node_id)
                if parent_id is not None:
                    f.write(f"Parent:\n")
                    parent_file_name = self.tree_data[parent_id].filename
                    relationship_to_parent = "child of"
                    try:
                        relationship_to_parent = self.tree_data[node_id].relationships[parent_id]
                    except Exception as e:
                        logging.error("Parent relationship not in tree_data")
                    relationship_to_parent = self.convert_to_snake_case(relationship_to_parent)
                    f.write(f"- {relationship_to_parent} [[{parent_file_name}]]\n")

                # Flush to ensure immediate file visibility
                f.flush()
                os.fsync(f.fileno())

        except (FileNotFoundError, IOError, OSError) as e:
            logging.error(
                f"Error writing Markdown file for node {node_id}: {e} - Type: {type(e)} - Traceback: {traceback.format_exc()}")
        except Exception as e:
            logging.error(
                f"Unexpected error writing Markdown file for node {node_id}: {e} - Type: {type(e)} - Traceback: {traceback.format_exc()}")

    @staticmethod
    def convert_to_snake_case(to_convert: str):
        return to_convert.replace(" ", "_")


    def get_parent_id(self, node_id):
        """Returns the parent ID of the given node, or None if it's the root."""
        for parent_id, node_data in self.tree_data.items():
            if node_id in node_data.children:
                return parent_id
        return None
