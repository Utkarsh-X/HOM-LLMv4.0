"""Prompt template loader."""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class TemplateLoader:
    """Loads and manages prompt templates."""

    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize template loader.
        
        Args:
            templates_dir: Directory containing template YAML files
        """
        if templates_dir is None:
            # Default to templates directory relative to this file
            templates_dir = Path(__file__).parent / "templates"
        self.templates_dir = templates_dir
        self._templates: dict[str, dict] = {}

    def load_template(self, name: str) -> Optional[str]:
        """
        Load template by name.
        
        Args:
            name: Template name (e.g., "explain")
        
        Returns:
            Template string or None if not found
        """
        if name in self._templates:
            return self._templates[name].get("template")

        template_path = self.templates_dir / f"{name}.yaml"
        if not template_path.exists():
            logger.warning(f"Template not found: {name}")
            return None

        try:
            with open(template_path, "r") as f:
                data = yaml.safe_load(f)
                self._templates[name] = data
                return data.get("template")
        except Exception as e:
            logger.error(f"Failed to load template {name}: {e}")
            return None

    def render(self, template_name: str, variables: dict) -> str:
        """
        Render template with variables.
        
        Args:
            template_name: Name of template
            variables: Variables to substitute
        
        Returns:
            Rendered template string
        """
        template = self.load_template(template_name)
        if template is None:
            # Fallback to simple template
            template = "{query}\n\n{context}"

        # Simple variable substitution
        try:
            return template.format(**variables)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")
            # Fill missing variables with empty string
            for key in variables:
                template = template.replace(f"{{{key}}}", str(variables.get(key, "")))
            return template
