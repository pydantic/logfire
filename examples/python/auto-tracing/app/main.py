from app.server import create_app


def main():
    """Entry point into app."""
    app = create_app()
    app.run(debug=True)


if __name__ == '__main__':
    main()
