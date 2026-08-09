"""The encoder receives an explicit token window, and the window is not small.

THE DEFECT THESE ARMS CLOSE. The encode call passed no `max_length`, so the
encoder applied its own default of 512 tokens. The measured median record in
the store runs to 1992 tokens, so a median record reached the semantic index at
roughly its first quarter and nothing reported the loss. `max_length` had ZERO
test hits in the memory layer, so no arm anywhere asserted that the call passed
a window at all.

NO ARM HERE WRITES A NUMBER. Each one imports the constant it compares against,
so the value lives in one place. A number written in two places goes stale in
one of them and nothing announces it.

NO ARM HERE RE-EMBEDS A RECORD, and that bound is deliberate. The vector write
path cannot replace a vector that is already stored, so a second write for one
memory raises. These arms assert at the CALL BOUNDARY, which needs no store and
no second write.

WHY THERE IS NO CHARACTER-SLICE ARM. The truncation has two arms in sequence. A
CHARACTER pre-slice keeps `max_length * model.median_token_length` characters,
then a TOKEN cut keeps `max_length` tokens. For text of density d characters
per token, `max_length` tokens occupy `max_length * d` characters, so the
pre-slice binds first only when d is above the multiplier. THE WINDOW CANCELS
OUT of that comparison. Measured across all 1819 records: minimum density
3.021, median 3.864, maximum 5.189. The multiplier for the configured model
measures 6. The maximum density sits below it, so the TOKEN cut binds for every
record and a character-slice arm would drive a branch nothing reaches.
THE ARGUMENT IS MODEL-SPECIFIC, not model-independent: the multiplier is a
property of the model rather than a constant of the library.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_PARENT = Path(__file__).parent.parent / "skills" / "pact-memory"
if str(SCRIPTS_PARENT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PARENT))

from scripts.embeddings import (  # noqa: E402
    EMBEDDING_MAX_TOKENS,
    MEASURED_MEDIAN_TOKENS,
    EmbeddingService,
)


class _RecordingModel:
    """Stands in for the encoder and records the call it receives.

    Deliberately NOT the real model. The subject here is the argument the
    service passes, so loading a model would add a download to an arm about
    one keyword.
    """

    def __init__(self):
        self.calls = []

    def encode(self, sentences, **kwargs):
        self.calls.append((sentences, kwargs))

        class _Row:
            def tolist(self_inner):
                return [0.0]

        return [_Row()]


def _service_with(model):
    service = EmbeddingService()
    service._model = model
    service._available = True
    return service


class TestTheEncoderReceivesTheWindow:
    def test_the_call_passes_the_window_constant(self):
        """RED IF THE KEYWORD IS DROPPED, which is the defect this ends.

        THE ARM CARRIES NO NUMBER. It imports the constant and compares against
        that name, so a later change to the window does not redden it and the
        value continues to live in one place.
        """
        model = _RecordingModel()
        _service_with(model).generate("some text to embed")

        # CONTROL: the encoder was reached at all, so an assertion about the
        # call below cannot pass against a call that never happened.
        assert len(model.calls) == 1

        _, kwargs = model.calls[0]
        assert "max_length" in kwargs, (
            "the encode call passes no window, so the encoder applies its own "
            "default and truncates a median record without reporting it"
        )
        assert kwargs["max_length"] == EMBEDDING_MAX_TOKENS


class TestTheWindowIsNotBelowTheMedianRecord:
    def test_the_window_is_not_below_the_measured_median(self):
        """RED IF SOMEBODY RETURNS THE WINDOW TO A TOO-SMALL VALUE.

        The wiring arm above catches a dropped keyword. It does NOT catch a
        window set back to the encoder default, which is the same fault this
        change exists to end. This arm covers that direction.

        IT REFERENCES TWO NAMES AND PINS NO LITERAL, so it survives a
        deliberate change to either constant and reddens on a regression.
        """
        assert EMBEDDING_MAX_TOKENS >= MEASURED_MEDIAN_TOKENS, (
            "the window is below the median record in the store, so a median "
            "record reaches the semantic index truncated"
        )
