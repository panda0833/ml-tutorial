import json
from pathlib import Path

import joblib
from sklearn.datasets import load_digits
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

ARTIFACTS_DIR = Path("artifacts")
MODEL_PATH = ARTIFACTS_DIR / "digits_logreg.joblib"
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"


def main() -> None:
    ARTIFACTS_DIR.mkdir(exist_ok=True)

    digits = load_digits()
    X = digits.data
    y = digits.target

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(
        max_iter=2000,
        solver="lbfgs",
        multi_class="auto",
    )
    model.fit(X_train_scaled, y_train)

    predictions = model.predict(X_test_scaled)
    accuracy = accuracy_score(y_test, predictions)

    report = classification_report(y_test, predictions, output_dict=True)
    metrics = {
        "accuracy": accuracy,
        "classification_report": report,
    }

    joblib.dump({"model": model, "scaler": scaler}, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))

    print(f"Saved model to: {MODEL_PATH}")
    print(f"Saved metrics to: {METRICS_PATH}")
    print(f"Accuracy: {accuracy:.4f}")


if __name__ == "__main__":
    main()
