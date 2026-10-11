import ai_manager
import io_manager


def main():
    """Collect shipments, have Gemini assess each one, and show the results."""
    assessments = ai_manager.assess_shipments(io_manager.input_method())
    io_manager.show_summary(assessments)
    io_manager.show_details(assessments)


if __name__ == "__main__":
    main()
