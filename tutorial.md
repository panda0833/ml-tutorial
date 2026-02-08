# Hands-On ML Tutorial: Handwritten Digits

This tutorial walks you through a full, minimal ML workflow using a free handwriting dataset.

## 1) Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) Explore the dataset

We use the **digits** dataset included with scikit-learn:

- 1,797 images of digits (0–9)
- Each image is 8x8 pixels (64 features)

See `src/visualize.py` to render sample images.

## 3) Train a model

Run the training script:

```bash
python src/train.py
```

It will:

- Load the dataset
- Split into train and test sets
- Train a `LogisticRegression` classifier
- Print accuracy and a classification report
- Save the model and metrics to `artifacts/`

## 4) Visualize results

```bash
python src/visualize.py
```

This script shows:

- A grid of sample digits
- A confusion matrix for the trained model

## 5) Make a prediction

```bash
python src/predict.py --index 0
```

This loads the model and predicts a single digit from the dataset.

## 6) Experiment ideas

- Compare classifiers (SVM vs. Logistic Regression)
- Add PCA and visualize in 2D
- Tune hyperparameters and compare accuracy

