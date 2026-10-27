"""R4 CPU-only selected-parent validation runner; no environment or training path."""
from preflight_prepare import validate

def main():
    result = validate()
    print(result)
    return result

if __name__ == "__main__":
    main()
