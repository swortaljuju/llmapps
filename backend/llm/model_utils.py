import copy

def flatten_schema_and_remove_defs(schema: dict) -> dict:
    """
    Remove $defs and replace all $ref with inline definitions
    """
    defs = schema.get("$defs", {})
    schema = copy.deepcopy(schema)
    if not defs:
        return schema

    def resolve_ref(obj):
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_key = obj["$ref"].split("/")[-1]
                return resolve_ref(defs[ref_key])
            else:
                return {k: resolve_ref(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [resolve_ref(i) for i in obj]
        else:
            return obj
    flat_schema = resolve_ref(schema)
    flat_schema.pop("$defs", None)
    return flat_schema