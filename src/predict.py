import argparse
from pathlib import Path

import joblib
from sklearn.datasets import load_digits

ARTIFACTS_DIR = Path("artifacts")
MODEL_PATH = ARTIFACTS_DIR / "digits_logreg.joblib"


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict a single digit sample.")
    parser.add_argument("--index", type=int, default=0, help="Dataset index to predict")
    args = parser.parse_args()

    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}. Run src/train.py first.")

    digits = load_digits()

    if args.index < 0 or args.index >= len(digits.data):
        raise ValueError(f"Index must be between 0 and {len(digits.data) - 1}")

    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]
    scaler = bundle["scaler"]

    sample = digits.data[args.index].reshape(1, -1)
    sample_scaled = scaler.transform(sample)
    prediction = model.predict(sample_scaled)[0]

    print(f"Predicted digit: {prediction}")
    print(f"True label: {digits.target[args.index]}")


if __name__ == "__main__":
    main()
