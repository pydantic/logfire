"""Demo: Variable Composition & Template Rendering with Logfire Managed Variables.

This script demonstrates the full power of Logfire's variable composition
(<<variable_name>> references) and Handlebars template rendering ({{field}})
using a purely local configuration — no remote server needed.

Key features shown:
  1. Basic variable composition: <<var>> references expand inline
  2. Nested composition: variable A references B, which references C
  3. Subfield variable references: <<var.field>> accesses a field of a structured variable
  4. Template rendering with {{field}} placeholders and Pydantic input models
  5. Accessing subfields of template inputs (e.g. {{user.name}}, {{user.email}})
  6. Handlebars conditionals: {{#if}}, {{else}}, {{/if}}
  7. Handlebars iteration: {{#each items}}...{{/each}}
  8. TemplateVariable: single-step get(inputs) with automatic rendering
  9. Variable.get() + .render(inputs): two-step manual rendering
  10. Rollout overrides with attribute-based conditions
  11. Composition-time conditionals: <<#if flag>>...<<else>>...<</if>>
"""

from __future__ import annotations

import json

from pydantic import BaseModel

import logfire
from logfire._internal.config import LocalVariablesOptions
from logfire.variables.config import (
    LabeledValue,
    Rollout,
    RolloutOverride,
    ValueEquals,
    VariableConfig,
    VariablesConfig,
)

# ---------------------------------------------------------------------------
# 1. Define Pydantic models for structured data & template inputs
# ---------------------------------------------------------------------------


class UserProfile(BaseModel):
    """Nested model used as a variable value (composed into other variables)."""

    name: str
    email: str
    tier: str = 'free'


class PromptInputs(BaseModel):
    """Template inputs with nested subfields."""

    user: UserProfile
    topic: str
    max_tokens: int = 500


class NotificationInputs(BaseModel):
    """Template inputs for notification templates."""

    user: UserProfile
    action: str
    details: str = ''


class OnboardingInputs(BaseModel):
    """Template inputs demonstrating conditionals and iteration."""

    user: UserProfile
    is_new_user: bool = True
    features: list[str] = []


# ---------------------------------------------------------------------------
# 2. Build a local VariablesConfig with several interconnected variables
# ---------------------------------------------------------------------------

variables_config = VariablesConfig(
    variables={
        # --- Leaf variables (no references to other variables) ---
        'app_name': VariableConfig(
            name='app_name',
            labels={
                'production': LabeledValue(version=1, serialized_value=json.dumps('Acme Platform')),
                'staging': LabeledValue(version=1, serialized_value=json.dumps('Acme Platform [STAGING]')),
            },
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[
                RolloutOverride(
                    conditions=[ValueEquals(attribute='environment', value='staging')],
                    rollout=Rollout(labels={'staging': 1.0}),
                ),
            ],
        ),
        'safety_disclaimer': VariableConfig(
            name='safety_disclaimer',
            labels={
                'production': LabeledValue(
                    version=1,
                    serialized_value=json.dumps(
                        'Always verify critical information independently. This AI assistant may make mistakes.'
                    ),
                ),
            },
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[],
        ),
        'support_email': VariableConfig(
            name='support_email',
            labels={
                'production': LabeledValue(version=1, serialized_value=json.dumps('help@acme.com')),
            },
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[],
        ),
        # --- Structured variable (JSON object) for subfield composition ---
        # Other variables can reference subfields like <<brand.tagline>>
        'brand': VariableConfig(
            name='brand',
            labels={
                'production': LabeledValue(
                    version=1,
                    serialized_value=json.dumps(
                        {
                            'tagline': 'Build faster, ship smarter',
                            'color': '#4F46E5',
                            'support_url': 'https://acme.dev/support',
                        }
                    ),
                ),
            },
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[],
        ),
        # --- Composed variable: references <<support_email>> ---
        'support_footer': VariableConfig(
            name='support_footer',
            labels={
                'production': LabeledValue(
                    version=1,
                    serialized_value=json.dumps('Need help? Contact us at <<support_email>>.'),
                ),
            },
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[],
        ),
        # --- Composed + templated variable ---
        # References <<app_name>>, <<safety_disclaimer>>, <<support_footer>>
        # Also contains {{user.name}}, {{user.tier}}, {{topic}} template placeholders
        'system_prompt': VariableConfig(
            name='system_prompt',
            labels={
                'production': LabeledValue(
                    version=1,
                    serialized_value=json.dumps(
                        'You are a helpful assistant for <<app_name>>.\n\n'
                        'The user you are speaking with is {{user.name}} ({{user.tier}} tier).\n'
                        'They want help with: {{topic}}\n\n'
                        'Guidelines:\n'
                        '- Be concise and helpful\n'
                        '- <<safety_disclaimer>>\n\n'
                        '<<support_footer>>'
                    ),
                ),
                'concise': LabeledValue(
                    version=1,
                    serialized_value=json.dumps(
                        '<<app_name>> assistant. User: {{user.name}} ({{user.tier}}). '
                        'Topic: {{topic}}. Be brief. <<safety_disclaimer>>'
                    ),
                ),
            },
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[],
            template_inputs_schema=PromptInputs.model_json_schema(),
        ),
        # --- Notification template: uses {{user.name}}, {{user.email}}, {{action}} ---
        # Also demonstrates {{#if details}} conditional
        'notification_template': VariableConfig(
            name='notification_template',
            labels={
                'production': LabeledValue(
                    version=1,
                    serialized_value=json.dumps(
                        'Hi {{user.name}},\n\n'
                        'Your action "{{action}}" has been completed on <<app_name>>.\n'
                        '{{#if details}}Details: {{details}}\n{{/if}}'
                        '\nA confirmation has been sent to {{user.email}}.\n\n'
                        '<<support_footer>>'
                    ),
                ),
            },
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[],
            template_inputs_schema=NotificationInputs.model_json_schema(),
        ),
        # --- Onboarding template: demonstrates #if/#else and #each ---
        # Also uses <<brand.tagline>> subfield composition
        'onboarding_message': VariableConfig(
            name='onboarding_message',
            labels={
                'production': LabeledValue(
                    version=1,
                    serialized_value=json.dumps(
                        '{{#if is_new_user}}'
                        'Welcome to <<app_name>>, {{user.name}}! '
                        '<<brand.tagline>>.\n'
                        '{{else}}'
                        'Welcome back to <<app_name>>, {{user.name}}!\n'
                        '{{/if}}'
                        '\n'
                        '{{#if features}}'
                        'Here are your enabled features:\n'
                        '{{#each features}}'
                        '  - {{this}}\n'
                        '{{/each}}'
                        '{{else}}'
                        'No features enabled yet. Visit <<brand.support_url>> to get started.\n'
                        '{{/if}}'
                        '\nQuestions? Reach out to <<support_email>>.'
                    ),
                ),
            },
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[],
            template_inputs_schema=OnboardingInputs.model_json_schema(),
        ),
        # --- Structured variable (JSON object) with template fields ---
        # Shows that templates work inside structured types, not just strings
        'welcome_config': VariableConfig(
            name='welcome_config',
            labels={
                'production': LabeledValue(
                    version=1,
                    serialized_value=json.dumps(
                        {
                            'greeting': 'Welcome to <<app_name>>, {{user.name}}!',
                            'subtitle': 'Your {{user.tier}} account is ready. <<brand.tagline>>.',
                            'cta_text': 'Explore {{topic}}',
                            'show_banner': True,
                            'max_tokens': 500,
                        }
                    ),
                ),
            },
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[],
            template_inputs_schema=PromptInputs.model_json_schema(),
        ),
        # --- Feature flag (boolean) for composition-time conditionals ---
        'beta_enabled': VariableConfig(
            name='beta_enabled',
            labels={
                'enabled': LabeledValue(version=1, serialized_value='true'),
                'disabled': LabeledValue(version=1, serialized_value='false'),
            },
            rollout=Rollout(labels={'enabled': 1.0}),
            overrides=[],
        ),
        # --- Composed variable using <<#if>> at composition time ---
        # The <<#if beta_enabled>> block is evaluated during composition, NOT at
        # template-render time. This means the conditional is resolved when the
        # variable value is expanded, controlled by the beta_enabled flag variable.
        'banner_message': VariableConfig(
            name='banner_message',
            labels={
                'production': LabeledValue(
                    version=1,
                    serialized_value=json.dumps(
                        '<<#if beta_enabled>>'
                        'Try our new beta features! <<brand.tagline>>.'
                        '<<else>>'
                        'Welcome to <<app_name>>.'
                        '<</if>>'
                    ),
                ),
            },
            rollout=Rollout(labels={'production': 1.0}),
            overrides=[],
        ),
    }
)

# ---------------------------------------------------------------------------
# 3. Configure Logfire with local variables (no remote server needed)
# ---------------------------------------------------------------------------

logfire.configure(
    send_to_logfire=False,
    variables=LocalVariablesOptions(
        config=variables_config,
        instrument=False,  # Keep output clean for the demo
    ),
)

# ---------------------------------------------------------------------------
# 4. Define variables in code
# ---------------------------------------------------------------------------

app_name_var = logfire.var('app_name', type=str, default='MyApp')
safety_var = logfire.var('safety_disclaimer', type=str, default='Be careful.')
support_email_var = logfire.var('support_email', type=str, default='support@example.com')
support_footer_var = logfire.var('support_footer', type=str, default='Contact support.')
brand_var = logfire.var(
    'brand',
    type=dict,
    default={'tagline': 'Default tagline', 'color': '#000', 'support_url': 'https://example.com'},
)

# A Variable with template_inputs — uses two-step get() + render()
system_prompt_var = logfire.var(
    'system_prompt',
    type=str,
    default='Hello {{user.name}}, how can I help with {{topic}}?',
    template_inputs=PromptInputs,
)

# TemplateVariables — single-step get(inputs) with automatic rendering
notification_var = logfire.template_var(
    'notification_template',
    type=str,
    default='Hi {{user.name}}, your {{action}} is done.',
    inputs_type=NotificationInputs,
)

onboarding_var = logfire.template_var(
    'onboarding_message',
    type=str,
    default='Welcome, {{user.name}}!',
    inputs_type=OnboardingInputs,
)

# Structured (dict) variable with templates inside
welcome_var = logfire.template_var(
    'welcome_config',
    type=dict,
    default={'greeting': 'Welcome, {{user.name}}!', 'show_banner': True, 'max_tokens': 500},
    inputs_type=PromptInputs,
)

# Composition-time conditional variable
banner_var = logfire.var('banner_message', type=str, default='Welcome.')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def section(title: str) -> None:
    """Print a section header."""
    print(f'\n{"=" * 70}')
    print(f'  {title}')
    print(f'{"=" * 70}\n')


# ---------------------------------------------------------------------------
# 5. Demo: Basic composition (no templates)
# ---------------------------------------------------------------------------

section('1. Basic Composition: <<variable>> references expand inline')

result = support_footer_var.get()
print(f'support_footer resolved to:\n  "{result.value}"\n')
print(f'Composed from {len(result.composed_from)} reference(s):')
for ref in result.composed_from:
    print(f'  - <<{ref.name}>> -> "{ref.value}" (label={ref.label}, v{ref.version})')

# ---------------------------------------------------------------------------
# 6. Demo: Nested composition (A -> B -> C)
# ---------------------------------------------------------------------------

section('2. Nested Composition: system_prompt -> support_footer -> support_email')

# Get the raw (unrendered) system prompt to see composition in action
raw_result = system_prompt_var.get()
print('After composition (before template rendering):')
print(f'  label={raw_result.label}, version={raw_result.version}')
print()

# Show the composed value — <<refs>> are expanded but {{fields}} remain
composed_value = raw_result.value
# Since templates haven't been rendered yet, {{...}} placeholders are literal
print('Composed value ({{placeholders}} still present):')
for line in composed_value.split('\n'):
    print(f'  {line}')

print(f'\nComposed from {len(raw_result.composed_from)} top-level reference(s):')
for ref in raw_result.composed_from:
    print(f'  - <<{ref.name}>> -> "{ref.value}"')
    # Show nested references (e.g. support_footer -> support_email)
    for nested in ref.composed_from:
        print(f'      -> <<{nested.name}>> -> "{nested.value}"')

# ---------------------------------------------------------------------------
# 7. Demo: Subfield references to structured variables
# ---------------------------------------------------------------------------

section('3. Subfield Variable References: <<brand.tagline>>, <<brand.support_url>>')

print('The "brand" variable is a JSON object:')
brand_result = brand_var.get()
for key, value in brand_result.value.items():
    print(f'  {key}: {value!r}')

print()
print('Other variables can reference individual fields via <<brand.field>>.')
print('For example, the onboarding_message template contains:')
print('  <<brand.tagline>>     -> expands to the tagline string')
print('  <<brand.support_url>> -> expands to the support URL string')

# ---------------------------------------------------------------------------
# 8. Demo: Handlebars conditionals (#if / #else)
# ---------------------------------------------------------------------------

section('4. Handlebars Conditionals: {{#if}}, {{else}}, {{/if}}')

print('The onboarding_message template uses conditionals:')
print('  {{#if is_new_user}}...welcome...{{else}}...welcome back...{{/if}}')
print('  {{#if features}}...list them...{{else}}...no features yet...{{/if}}')
print()

# New user WITH features
new_user_inputs = OnboardingInputs(
    user=UserProfile(name='Alice', email='alice@example.com'),
    is_new_user=True,
    features=['Dashboard Analytics', 'API Access', 'Team Management'],
)

result_new = onboarding_var.get(new_user_inputs)
print('--- New user with features ---')
for line in result_new.value.split('\n'):
    print(f'  {line}')

print()

# Returning user WITHOUT features
returning_user_inputs = OnboardingInputs(
    user=UserProfile(name='Bob', email='bob@example.com', tier='premium'),
    is_new_user=False,
    features=[],
)

result_returning = onboarding_var.get(returning_user_inputs)
print('--- Returning user, no features ---')
for line in result_returning.value.split('\n'):
    print(f'  {line}')

print()
print('Composed references in the onboarding message:')
for ref in result_new.composed_from:
    print(f'  - <<{ref.name}>> -> "{ref.value}"')

# ---------------------------------------------------------------------------
# 9. Demo: Template rendering with subfield access (user.name, user.tier)
# ---------------------------------------------------------------------------

section('5. Template Rendering: Subfields of inputs ({{user.name}}, {{user.tier}})')

user = UserProfile(name='Alice Johnson', email='alice@example.com', tier='premium')
inputs = PromptInputs(user=user, topic='billing questions')

# Two-step: get() then render()
with system_prompt_var.get() as resolved:
    rendered = resolved.render(inputs)

print('Rendered system prompt:')
for line in rendered.split('\n'):
    print(f'  {line}')

# ---------------------------------------------------------------------------
# 10. Demo: TemplateVariable single-step get(inputs)
# ---------------------------------------------------------------------------

section('6. TemplateVariable: Single-step get(inputs) with auto-rendering')

# {{#if details}} conditional: included because details is non-empty
notif_inputs = NotificationInputs(
    user=UserProfile(name='Bob Smith', email='bob@corp.com', tier='enterprise'),
    action='project deployment',
    details='Deployed v2.3.1 to production',
)

result = notification_var.get(notif_inputs)
print('--- With details ({{#if details}} is truthy) ---')
for line in result.value.split('\n'):
    print(f'  {line}')

print()

# {{#if details}} conditional: omitted because details is empty
notif_no_details = NotificationInputs(
    user=UserProfile(name='Carol', email='carol@startup.io'),
    action='password reset',
)

result_no_details = notification_var.get(notif_no_details)
print('--- Without details ({{#if details}} is falsy) ---')
for line in result_no_details.value.split('\n'):
    print(f'  {line}')

# ---------------------------------------------------------------------------
# 11. Demo: Structured variable with templates and subfield composition
# ---------------------------------------------------------------------------

section('7. Structured Variable: Templates + <<brand.tagline>> in dict values')

struct_inputs = PromptInputs(
    user=UserProfile(name='Carol', email='carol@startup.io'),
    topic='AI integrations',
)

struct_result = welcome_var.get(struct_inputs)
print('Rendered welcome_config (dict with templates in string fields):')
for key, value in struct_result.value.items():
    print(f'  {key}: {value!r}')

print('\nNote: string values were rendered, non-strings (bool, int) pass through unchanged.')
print('The subtitle used <<brand.tagline>> to compose in the brand tagline.')

# ---------------------------------------------------------------------------
# 12. Demo: Rollout overrides with attributes
# ---------------------------------------------------------------------------

section('8. Rollout Overrides: Attribute-based label selection')

prod_result = app_name_var.get()
print(f'Default (production):  "{prod_result.value}" (label={prod_result.label})')

staging_result = app_name_var.get(attributes={'environment': 'staging'})
print(f'With env=staging:      "{staging_result.value}" (label={staging_result.label})')

# ---------------------------------------------------------------------------
# 13. Demo: Explicit label selection
# ---------------------------------------------------------------------------

section('9. Explicit Label Selection: Choosing a specific label')

verbose_result = system_prompt_var.get(label='production')
concise_result = system_prompt_var.get(label='concise')

print('Production prompt (first 80 chars):')
print(f'  "{verbose_result.value[:80]}..."')
print('\nConcise prompt:')
print(f'  "{concise_result.value}"')

# Now render the concise one with template inputs
rendered_concise = concise_result.render(inputs)
print('\nConcise prompt rendered:')
print(f'  "{rendered_concise}"')

# ---------------------------------------------------------------------------
# 14. Demo: Composition-time conditionals (<<#if>> at composition time)
# ---------------------------------------------------------------------------

section('10. Composition-Time Conditionals: <<#if>> with feature flags')

print('The banner_message variable uses <<#if beta_enabled>> at composition time.')
print('This conditional is resolved when <<>> references are expanded, NOT at')
print('template render time. The beta_enabled variable controls which branch appears.')
print()

# beta_enabled is true by default (the "enabled" label has weight 1.0)
banner_result = banner_var.get()
print('With beta_enabled=true:')
print(f'  "{banner_result.value}"')
print()

# Show the composed references
print(f'Composed from {len(banner_result.composed_from)} reference(s):')
for ref in banner_result.composed_from:
    print(f'  - <<{ref.name}>> = {ref.value!r}')

# ---------------------------------------------------------------------------
# 15. Demo: Using context manager for baggage propagation
# ---------------------------------------------------------------------------

section('11. Context Manager: Baggage propagation for observability')

with system_prompt_var.get() as resolved:
    print('Inside context manager:')
    print(f'  Variable: {resolved.name}')
    print(f'  Label: {resolved.label}')
    print(f'  Version: {resolved.version}')
    print(f'  Baggage key: logfire.variables.{resolved.name}')
    print(f'  Baggage value: {resolved.label}')
    print()
    print('  Any spans created in this block will carry the variable')
    print('  resolution as baggage, enabling downstream correlation.')

# ---------------------------------------------------------------------------
# 16. Summary
# ---------------------------------------------------------------------------

section('Summary')
print('This demo showed:')
print('  - <<variable>> composition: inline expansion of variable references')
print('  - Nested composition: A -> B -> C chains expand recursively')
print('  - <<var.field>> subfield refs: access fields of structured variables')
print('  - {{field}} templates with Handlebars syntax')
print('  - Subfield access in templates: {{user.name}}, {{user.email}}, {{user.tier}}')
print('  - {{#if cond}}...{{else}}...{{/if}} conditionals (template-time)')
print('  - {{#each list}}...{{/each}} iteration (template-time)')
print('  - <<#if flag>>...<<else>>...<</if>> conditionals (composition-time)')
print('  - Structured variables: templates render inside dict string values')
print('  - TemplateVariable: single-step get(inputs) with auto-rendering')
print('  - Variable + render(): two-step manual rendering')
print('  - Rollout overrides: attribute-based label selection')
print('  - Explicit label selection: get(label="concise")')
print('  - Context manager: baggage propagation for observability')
print()
print('All using LocalVariablesOptions — no remote server required!')
