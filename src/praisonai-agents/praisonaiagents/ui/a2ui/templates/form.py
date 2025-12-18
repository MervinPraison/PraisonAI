"""
Form Template for A2UI

Provides a form UI template for data collection.
"""

from typing import Any, Dict, List

from praisonaiagents.ui.a2ui.surface import Surface
from praisonaiagents.ui.a2ui.types import PathBinding
from praisonaiagents.ui.a2ui.extension import STANDARD_CATALOG_ID


class FormTemplate:
    """
    Form UI template for data collection.
    
    Creates a form with various input fields and a submit button.
    
    Example:
        >>> template = FormTemplate(surface_id="form", title="Contact")
        >>> template.add_text_field(id="name", label="Name")
        >>> template.add_email_field(id="email", label="Email")
        >>> template.set_submit_action("submit_form", "Send")
        >>> messages = template.to_messages()
    """
    
    def __init__(
        self,
        surface_id: str = "form",
        title: str = "Form",
        catalog_id: str = STANDARD_CATALOG_ID,
    ):
        """
        Initialize FormTemplate.
        
        Args:
            surface_id: Unique ID for the surface
            title: Form title
            catalog_id: Component catalog to use
        """
        self.surface_id = surface_id
        self.title = title
        self.catalog_id = catalog_id
        self.fields: List[Dict[str, Any]] = []
        self.submit_action = "submit"
        self.submit_label = "Submit"
    
    def add_text_field(
        self,
        id: str,
        label: str,
        default: str = "",
        required: bool = False,
    ) -> "FormTemplate":
        """
        Add a text input field.
        
        Args:
            id: Field ID
            label: Field label
            default: Default value
            required: Whether field is required
        
        Returns:
            self for chaining
        """
        self.fields.append({
            "id": id,
            "label": label,
            "type": "text",
            "default": default,
            "required": required,
        })
        return self
    
    def add_number_field(
        self,
        id: str,
        label: str,
        default: float = 0,
        required: bool = False,
    ) -> "FormTemplate":
        """
        Add a number input field.
        
        Args:
            id: Field ID
            label: Field label
            default: Default value
            required: Whether field is required
        
        Returns:
            self for chaining
        """
        self.fields.append({
            "id": id,
            "label": label,
            "type": "number",
            "default": default,
            "required": required,
        })
        return self
    
    def add_email_field(
        self,
        id: str,
        label: str,
        default: str = "",
        required: bool = False,
    ) -> "FormTemplate":
        """
        Add an email input field.
        
        Args:
            id: Field ID
            label: Field label
            default: Default value
            required: Whether field is required
        
        Returns:
            self for chaining
        """
        self.fields.append({
            "id": id,
            "label": label,
            "type": "email",
            "default": default,
            "required": required,
        })
        return self
    
    def set_submit_action(
        self,
        action: str,
        label: str = "Submit",
    ) -> "FormTemplate":
        """
        Set the submit button action.
        
        Args:
            action: Action name
            label: Button label
        
        Returns:
            self for chaining
        """
        self.submit_action = action
        self.submit_label = label
        return self
    
    def to_messages(self) -> List[Dict[str, Any]]:
        """
        Generate A2UI messages for the form.
        
        Returns:
            List of A2UI message dictionaries
        """
        surface = Surface(
            surface_id=self.surface_id,
            catalog_id=self.catalog_id,
        )
        
        # Title
        surface.text(id="form-title", text=self.title, usage_hint="h1")
        
        # Fields
        field_ids = []
        for field in self.fields:
            field_id = field["id"]
            surface.text_field(
                id=field_id,
                label=field["label"],
                text=PathBinding(path=f"/{field_id}"),
                field_type=field["type"],
            )
            field_ids.append(field_id)
            
            # Set default value
            surface.set_data(field_id, field.get("default", ""))
        
        # Submit button
        surface.text(id="submit-text", text=self.submit_label)
        
        action_context = [
            {"key": f["id"], "value": {"path": f"/{f['id']}"}}
            for f in self.fields
        ]
        
        surface.button(
            id="submit-btn",
            child="submit-text",
            action_name=self.submit_action,
            action_context=action_context,
            primary=True,
        )
        field_ids.append("submit-btn")
        
        # Form fields column
        surface.column(id="fields", children=field_ids)
        
        # Root column
        surface.column(id="root", children=["form-title", "fields"])
        
        return surface.to_messages()
