import ai_manager
import io_manager


def main():
    """Collect shipments, have Gemini assess each one, and show the results."""
    io_manager.show_assessments(ai_manager.assess_shipments(io_manager.input_method()))


if __name__ == "__main__":
    main()
