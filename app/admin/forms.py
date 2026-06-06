"""WTForms classes for the admin UI."""

from __future__ import annotations

import json

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DecimalField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    EqualTo,
    Length,
    Optional,
    Regexp,
    ValidationError,
)

# Loose email check — avoids pulling in the optional `email_validator` dependency
# that WTForms' Email() requires. Good enough to catch obvious typos.
_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=64)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=256)])
    submit = SubmitField("Sign in")


def _json_validator(form, field):
    if not field.data:
        return
    try:
        loaded = json.loads(field.data)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON: {e}") from e
    if not isinstance(loaded, dict):
        raise ValidationError("Metadata must be a JSON object")


class GameForm(FlaskForm):
    name = StringField(
        "Name", validators=[DataRequired(), Length(min=1, max=128)]
    )
    slug = StringField(
        "Slug (URL identifier)",
        validators=[
            DataRequired(),
            Length(min=2, max=64),
            Regexp(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$"),
        ],
    )
    timezone = SelectField("Timezone", validators=[DataRequired()])
    score_direction = SelectField(
        "Score direction",
        choices=[("desc", "Higher is better (default)"), ("asc", "Lower is better (racing)")],
        validators=[DataRequired()],
    )
    min_score = DecimalField(
        "Minimum allowed score",
        validators=[Optional()],
        places=6,
    )
    max_score = DecimalField(
        "Maximum allowed score",
        validators=[Optional()],
        places=6,
    )
    metadata_json = TextAreaField(
        "Metadata (JSON)",
        default="{}",
        validators=[Optional(), _json_validator],
    )
    operator_name = StringField(
        "Operator / developer name (shown on the privacy policy)",
        validators=[Optional(), Length(max=128)],
    )
    contact_email = StringField(
        "Privacy contact email (shown on the privacy policy)",
        validators=[
            Optional(),
            Length(max=254),
            Regexp(_EMAIL_RE, message="Enter a valid email address."),
        ],
    )
    privacy_policy_extra = TextAreaField(
        "Additional privacy-policy clauses (optional, plain text)",
        validators=[Optional(), Length(max=20000)],
    )
    archived = BooleanField("Archived (hidden from public API)")
    submit = SubmitField("Save")


class NewAdminForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=1, max=64)],
    )
    password = PasswordField(
        "Password (min 12 chars)",
        validators=[DataRequired(), Length(min=12, max=256)],
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", "Passwords must match")],
    )
    submit = SubmitField("Create admin")
