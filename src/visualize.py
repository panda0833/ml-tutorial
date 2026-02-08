from pathlib import Path

import joblib
import matplotlib
import matplotlib.pyplot as plt
from sklearn.datasets import load_digits
from sklearn.metrics import ConfusionMatrixDisplay

matplotlib.use("Agg")

ARTIFACTS_DIR = Path("artifacts")
MODEL_PATH = ARTIFACTS_DIR / "digits_logreg.joblib"
SAMPLES_PATH = ARTIFACTS_DIR / "digits_samples.png"
CONFUSION_PATH = ARTIFACTS_DIR / "confusion_matrix.png"


def save_sample_grid() -> None:
    digits = load_digits()
    images = digits.images[:16]

    fig, axes = plt.subplots(4, 4, figsize=(6, 6))
    for ax, image in zip(axes.ravel(), images):
        ax.imshow(image, cmap="gray")
        ax.axis("off")
    fig.suptitle("Sample Digits")
    fig.tight_layout()
    fig.savefig(SAMPLES_PATH, dpi=150)
    plt.close(fig)


def save_confusion_matrix() -> None:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}. Run src/train.py first."
        )

    digits = load_digits()
    X = digits.data
    y = digits.target

    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]
    scaler = bundle["scaler"]

    X_scaled = scaler.transform(X)
    predictions = model.predict(X_scaled)

    fig, ax = plt.subplots(figsize=(6, 6))
    ConfusionMatrixDisplay.from_predictions(
        y,
        predictions,
        ax=ax,
        cmap="Blues",
        colorbar=False,
    )
    ax.set_title("Confusion Matrix")
    fig.tight_layout()
    fig.savefig(CONFUSION_PATH, dpi=150)
    plt.close(fig)


def main() -> None:
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    save_sample_grid()
    save_confusion_matrix()
    print(f"Saved sample grid to: {SAMPLES_PATH}")
    print(f"Saved confusion matrix to: {CONFUSION_PATH}")


if __name__ == "__main__":
    main()
