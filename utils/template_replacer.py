def recursive_replace(value: dict, replacements: dict) -> dict:
    """
    Recursively replaces templates in a value.
    """
    # If the value is a dictionary, recurse through its items.
    if isinstance(value, dict):
        return {k: recursive_replace(v, replacements) for k, v in value.items()}

    # If the value is a list, recurse through its items.
    elif isinstance(value, list):
        return [recursive_replace(item, replacements) for item in value]

    # If the value is a string, check for replacements.
    elif isinstance(value, str):
        # Exact match replacement (e.g., "$dict_value" -> {"new": "dict"})
        if value in replacements:
            return replacements[value]

        # Substring replacement (e.g., "prefix_$string_value" -> "prefix_10:00")
        for old_template, new_value in replacements.items():
            if isinstance(new_value, str) and old_template in value:
                return value.replace(old_template, new_value)

    # Return the value as is if no replacement is needed.
    return value
