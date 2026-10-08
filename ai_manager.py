"""ai_manager: the AI side of the pipeline, no domain logic.

It builds prompts, defines the response the AI must return, validates that
response and hands the result on. All network calls live in api_client.py.
"""
