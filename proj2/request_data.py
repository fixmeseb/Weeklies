"""Reading a request's JSON body and page number, whatever was sent."""

import math

from flask import abort, jsonify, make_response, request


def json_object() -> dict:
    """
    The request's JSON body

    Returns:
        dict: The body; empty when there is none or it is not valid JSON

    Raises:
        HTTPException: 400, as JSON, for a body that is valid JSON but not an object
    """
    body = request.get_json(silent=True)
    if body is None:
        return {}
    if not isinstance(body, dict):
        answer = {"ok": False, "error": "invalid_json", "message": "Send a JSON object."}
        abort(make_response(jsonify(answer), 400))
    return body


def page_number(total: int, per_page: int):
    """
    The ?page= of a list

    Args:
        total (int): How many entries the list has
        per_page (int): How many entries a page shows

    Returns:
        Tuple[int, int]: (page, pages). A page that is not a number is the first, and one
            past the end is the last.
    """
    pages = max(1, math.ceil(total / per_page))
    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1
    return min(max(page, 1), pages), pages
