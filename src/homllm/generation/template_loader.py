"""Prompt template loader."""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# ABRM template name (Plan C)
ABRM_TEMPLATE_NAME = "abrm_explain"


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

    def select_template(
        self,
        base_template: str,
        abrm_active: bool = False,
    ) -> str:
        """
        Select appropriate template based on ABRM state.
        
        Plan C: ABRM (Assumption-Bound Reasoning Mode) template selection.
        
        Args:
            base_template: Default template name (e.g., "explain")
            abrm_active: Whether ABRM is activated
        
        Returns:
            Template name to use
        """
        if abrm_active:
            # Check if ABRM template exists
            abrm_path = self.templates_dir / f"{ABRM_TEMPLATE_NAME}.yaml"
            if abrm_path.exists():
                logger.info(f"ABRM activated: using template {ABRM_TEMPLATE_NAME}")
                return ABRM_TEMPLATE_NAME
            else:
                logger.warning(f"ABRM template not found: {ABRM_TEMPLATE_NAME}, using base")
        
        return base_template

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

        # Merge template-defined sections (e.g., instruction, structure) into variables
        template_data = self._templates.get(template_name, {})
        merged_variables = dict(variables)
        for key in ("instruction", "query_header", "context_header", "provenance_header", "structure", "task"):
            if key in template_data and key not in merged_variables:
                merged_variables[key] = template_data.get(key, "")

        # Expand nested placeholders inside section fields (e.g., query_header contains {query})
        class _SafeDict(dict):
            def __missing__(self, key):
                return ""

        for key in ("instruction", "query_header", "context_header", "provenance_header", "structure", "task"):
            value = merged_variables.get(key)
            if isinstance(value, str):
                merged_variables[key] = value.format_map(_SafeDict(merged_variables))

        # Simple variable substitution with safe fallback for missing keys
        try:
            rendered = template.format(**merged_variables)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")
            rendered = template.format_map(_SafeDict(merged_variables))

        # Debug excerpt for prompt rendering
        excerpt = rendered[:200].replace("\n", " ")
        logger.info("PROMPT_RENDER excerpt=%s", excerpt)
        return rendered

    def render_with_abrm(
        self,
        base_template: str,
        variables: dict,
        abrm_active: bool = False,
        mechanical_fix_notice: str = "",
    ) -> str:
        """
        Render template with ABRM support.
        
        Plan C: Convenience method that handles ABRM template selection
        and injects mechanical fix notice.
        
        Args:
            base_template: Default template name
            variables: Template variables
            abrm_active: Whether ABRM is activated
            mechanical_fix_notice: Provenance priming notice from mechanical fixer
        
        Returns:
            Rendered template string
        """
        # Select appropriate template
        template_name = self.select_template(base_template, abrm_active)
        
        # Add mechanical fix notice to variables
        full_variables = {
            **variables,
            "mechanical_fix_notice": mechanical_fix_notice,
        }
        
        return self.render(template_name, full_variables)

