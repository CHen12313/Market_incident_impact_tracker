"""Compare each company's predicted direction against its actual market reaction."""
from Data_Classes.enums import Direction
from Data_Classes.event import Impact
from Data_Classes.pipeline import PipelineContext
from Pipeline.pipeline_module import PipelineModule


class PredictionChecker(PipelineModule):
    """
    Reads `context.events[].impacts` (EventStudyRunner's output), compares
    each impact's expected direction against its measured abnormal return,
    and writes `impact.prediction_match` / `impact.study.verdict_text` —
    see DATA_CONTRACT.md.
    """

    label = "Checking predictions"

    async def run(self, context: PipelineContext) -> tuple[str | None, bool]:
        for record in context.events:
            self.check_predictions(record.impacts)
        return None, True

    @staticmethod
    def check_predictions(impacts: list[Impact]) -> None:
        for impact in impacts:
            study = impact.study
            direction = impact.expected_direction
            cumulative_abnormal_return, t_statistic = study.car_pct, study.t_stat
            impact.prediction_match = None
            if study.is_significant:
                moved = "Rose" if cumulative_abnormal_return > 0 else "Fell"
                if direction != Direction.UNCLEAR:
                    impact.prediction_match = (cumulative_abnormal_return > 0) == (direction == Direction.UP)
                study.verdict_text = (
                    f"{moved} {abs(cumulative_abnormal_return):.2f}% relative to the market-based expectation "
                    f"over {study.days_after + 1} trading days (t = {t_statistic:.2f})."
                )
            else:
                study.verdict_text = f"Moved roughly in line with the market (t = {t_statistic:.2f})."
