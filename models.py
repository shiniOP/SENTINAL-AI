# models.py

from types import SimpleNamespace

from langchain_google_genai import ChatGoogleGenerativeAI

from config import (
    PRIMARY_MODEL,
    FALLBACK_MODELS,
)


# ============================================================
# CONTENT NORMALIZATION
# ============================================================

def normalize_content(content):
    """
    Gemini may return content as either:

        "plain string"

    or:

        [
            {"type": "text", "text": "..."},
            ...
        ]

    Normalize both formats into a plain string.
    """

    if isinstance(content, str):
        return content

    if isinstance(content, list):

        parts = []

        for item in content:

            if isinstance(item, str):

                parts.append(item)

            elif isinstance(item, dict):

                text = item.get(
                    "text",
                    ""
                )

                if text:
                    parts.append(str(text))

            else:

                text = getattr(
                    item,
                    "text",
                    None
                )

                if text:
                    parts.append(str(text))

        return "\n".join(parts)

    if content is None:
        return ""

    return str(content)


# ============================================================
# MODEL CREATION
# ============================================================

def create_llm(model_name=None):

    if model_name is None:

        model_name = PRIMARY_MODEL

    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0,
    )


# ============================================================
# MODEL LIST
# ============================================================

def get_model_names():

    return [
        PRIMARY_MODEL,
        *FALLBACK_MODELS,
    ]


# ============================================================
# NORMAL LLM INVOCATION
# ============================================================

def invoke_with_fallback(prompt):

    errors = []

    for model_name in get_model_names():

        try:

            print(
                f"\n[MODEL] Trying: {model_name}"
            )

            llm = create_llm(
                model_name
            )

            response = llm.invoke(
                prompt
            )

            # ------------------------------------------------
            # Normalize Gemini content
            # ------------------------------------------------

            normalized_content = (
                normalize_content(
                    response.content
                )
            )

            # ------------------------------------------------
            # Return a lightweight response
            # compatible with existing agents:
            #
            # result.content
            # ------------------------------------------------

            normalized_response = (
                SimpleNamespace(
                    content=normalized_content
                )
            )

            print(
                f"[MODEL] Success: {model_name}"
            )

            return (
                normalized_response,
                model_name
            )

        except Exception as e:

            print(
                f"[MODEL] Failed: {model_name}"
            )

            errors.append(
                {
                    "model": model_name,
                    "error": str(e),
                }
            )

    raise RuntimeError(
        f"All Gemini models failed: {errors}"
    )


# ============================================================
# STRUCTURED LLM INVOCATION
# ============================================================

def invoke_structured_with_fallback(
    prompt,
    schema,
):

    errors = []

    for model_name in get_model_names():

        try:

            print(
                f"\n[MODEL] Trying structured: "
                f"{model_name}"
            )

            llm = create_llm(
                model_name
            )

            structured_llm = (
                llm.with_structured_output(
                    schema
                )
            )

            response = (
                structured_llm.invoke(
                    prompt
                )
            )

            print(
                f"[MODEL] Success: {model_name}"
            )

            return (
                response,
                model_name
            )

        except Exception as e:

            print(
                f"[MODEL] Failed: {model_name}"
            )

            errors.append(
                {
                    "model": model_name,
                    "error": str(e),
                }
            )

    raise RuntimeError(
        "All Gemini structured models failed: "
        f"{errors}"
    )