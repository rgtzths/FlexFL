import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from flexfl.builtins.MLFrameworkABC import MLFrameworkABC


class _FakeML(MLFrameworkABC):

    @property
    def prefix(self) -> str:
        return "fake"

    def set_seed(self, seed):
        pass

    def setup(self):
        pass

    def load_data(self, split):
        pass

    def get_weights(self):
        return None

    def set_weights(self, weights):
        pass

    def calculate_gradients(self):
        return None

    def apply_gradients(self, gradients):
        pass

    def train(self, epochs, verbose=False):
        pass

    def predict(self, data):
        return None

    def calculate_loss(self, y_true, y_pred):
        return 0.0

    def save_model(self, path):
        pass

    def load_model(self, path):
        pass
