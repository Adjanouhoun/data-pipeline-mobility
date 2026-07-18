{% macro prevent_unapproved_full_refresh() %}

    {% if flags.FULL_REFRESH
        and not var('allow_destructive_full_refresh', false) %}

        {{
            exceptions.raise_compiler_error(
                "Full refresh blocked for protected historical model "
                ~ model.name
                ~ ". Use --vars "
                ~ "'{\"allow_destructive_full_refresh\": true}' "
                ~ "only after a verified backup and explicit approval."
            )
        }}

    {% endif %}

{% endmacro %}