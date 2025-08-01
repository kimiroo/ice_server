def replace_values_in_dict(d, old_template, new_value):
    """
    Recursively replaces a template string in all values of a dictionary.

    Args:
        d (dict): The dictionary to search and modify.
        old_template (str): The template string to be replaced (e.g., "$replace").
        new_value (str): The string to replace the template with.
    """
    if isinstance(d, dict):
        for k, v in d.items():
            # If the value is a dictionary, call the function recursively
            if isinstance(v, dict):
                replace_values_in_dict(v, old_template, new_value)
            # If the value is a string and contains the template, replace it
            elif isinstance(v, str) and old_template in v:
                d[k] = v.replace(old_template, new_value)
            # If the value is a list, iterate through its items
            elif isinstance(v, list):
                # We need to use list comprehension or a for loop to modify the list in place
                # Here's a simple for loop example
                for i in range(len(v)):
                    if isinstance(v[i], str) and old_template in v[i]:
                        v[i] = v[i].replace(old_template, new_value)
                    elif isinstance(v[i], dict):
                        replace_values_in_dict(v[i], old_template, new_value)