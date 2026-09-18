from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.db.models import Dataset, ForecastPoint, ForecastRun, InsightReport, SalesObservation
from src.schemas import DatasetCreate, DatasetRead, ForecastRunCreate, ForecastRunRead


class DatasetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_with_observations(self, payload: DatasetCreate) -> Dataset:
        dataset = Dataset(
            name=payload.name,
            source_filename=payload.source_filename,
            frequency=payload.frequency,
            target_kpi=payload.target_kpi,
            column_mapping=payload.column_mapping,
            quality_report=payload.quality_report,
            status=payload.status,
        )
        self.session.add(dataset)
        self.session.flush()

        observations = [
            SalesObservation(
                dataset_id=dataset.id,
                ds=item.ds,
                y=item.y,
                series_key=item.series_key,
                dimensions=item.dimensions,
                drivers=item.drivers,
                is_transformed=item.is_transformed,
            )
            for item in payload.observations
        ]
        if observations:
            self.session.add_all(observations)
        self.session.flush()
        self.session.refresh(dataset)
        return dataset

    def get_by_id(self, dataset_id: int) -> Dataset | None:
        stmt = (
            select(Dataset)
            .where(Dataset.id == dataset_id)
            .options(selectinload(Dataset.observations))
        )
        return self.session.scalars(stmt).first()

    def list_summaries(self) -> list[DatasetRead]:
        count_subq = (
            select(
                SalesObservation.dataset_id.label("dataset_id"),
                func.count(SalesObservation.id).label("observations_count"),
            )
            .group_by(SalesObservation.dataset_id)
            .subquery()
        )
        stmt = (
            select(Dataset, func.coalesce(count_subq.c.observations_count, 0))
            .outerjoin(count_subq, Dataset.id == count_subq.c.dataset_id)
            .order_by(Dataset.id.desc())
        )
        rows = self.session.execute(stmt).all()
        result: list[DatasetRead] = []
        for dataset, observations_count in rows:
            item = DatasetRead.model_validate(dataset)
            item.observations_count = int(observations_count)
            result.append(item)
        return result

    def delete_by_id(self, dataset_id: int) -> bool:
        dataset = self.session.get(Dataset, dataset_id)
        if dataset is None:
            return False
        self.session.delete(dataset)
        self.session.flush()
        return True

    def list_series_keys(self, dataset_id: int) -> list[str]:
        stmt = (
            select(SalesObservation.series_key)
            .where(SalesObservation.dataset_id == dataset_id)
            .distinct()
            .order_by(SalesObservation.series_key)
        )
        return list(self.session.scalars(stmt).all())

    def list_dimension_values(self, dataset_id: int, dimension_key: str) -> list[str]:
        # JSONB extraction; values stored as text for filter UI
        stmt = select(SalesObservation.dimensions).where(SalesObservation.dataset_id == dataset_id)
        values: set[str] = set()
        for payload in self.session.scalars(stmt).all():
            if isinstance(payload, dict) and dimension_key in payload and payload[dimension_key] is not None:
                values.add(str(payload[dimension_key]))
        return sorted(values)

    def load_observations(
        self,
        dataset_id: int,
        *,
        series_key: str | None = None,
    ) -> list[SalesObservation]:
        stmt = (
            select(SalesObservation)
            .where(SalesObservation.dataset_id == dataset_id)
            .order_by(SalesObservation.ds.asc())
        )
        if series_key:
            stmt = stmt.where(SalesObservation.series_key == series_key)
        return list(self.session.scalars(stmt).all())

    def save_forecast_run(self, payload: ForecastRunCreate) -> ForecastRun:
        run = ForecastRun(
            dataset_id=payload.dataset_id,
            series_key=payload.series_key,
            model_name=payload.model_name,
            model_version=payload.model_version,
            train_start=payload.train_start,
            train_end=payload.train_end,
            horizon=payload.horizon,
            config=payload.config,
            metrics=payload.metrics,
            quality_status=payload.quality_status,
        )
        self.session.add(run)
        self.session.flush()
        points = [
            ForecastPoint(
                run_id=run.id,
                ds=item.ds,
                yhat=item.yhat,
                yhat_lower=item.yhat_lower,
                yhat_upper=item.yhat_upper,
                scenario_type=item.scenario_type,
                scenario_factors=item.scenario_factors,
            )
            for item in payload.points
        ]
        if points:
            self.session.add_all(points)
        self.session.flush()
        self.session.refresh(run)
        return run

    def list_forecast_runs(self, dataset_id: int, *, limit: int = 20) -> list[ForecastRunRead]:
        count_subq = (
            select(
                ForecastPoint.run_id.label("run_id"),
                func.count(ForecastPoint.id).label("points_count"),
            )
            .group_by(ForecastPoint.run_id)
            .subquery()
        )
        stmt = (
            select(ForecastRun, func.coalesce(count_subq.c.points_count, 0))
            .outerjoin(count_subq, ForecastRun.id == count_subq.c.run_id)
            .where(ForecastRun.dataset_id == dataset_id)
            .order_by(ForecastRun.id.desc())
            .limit(limit)
        )
        rows = self.session.execute(stmt).all()
        result: list[ForecastRunRead] = []
        for run, points_count in rows:
            item = ForecastRunRead.model_validate(run)
            item.points_count = int(points_count)
            result.append(item)
        return result

    def load_forecast_points(self, run_id: int) -> list[ForecastPoint]:
        stmt = (
            select(ForecastPoint)
            .where(ForecastPoint.run_id == run_id)
            .order_by(ForecastPoint.ds.asc())
        )
        return list(self.session.scalars(stmt).all())

    def save_insight_report(
        self,
        *,
        run_id: int,
        facts: dict,
        recommendations: dict,
        source: str,
        openai_model: str | None = None,
        notes: str | None = None,
    ) -> InsightReport:
        report = InsightReport(
            run_id=run_id,
            facts=facts,
            recommendations=recommendations,
            source=source,
            openai_model=openai_model,
            notes=notes,
        )
        self.session.add(report)
        self.session.flush()
        self.session.refresh(report)
        return report

    def get_insight_by_facts_hash(self, facts_hash: str, *, limit_scan: int = 50) -> InsightReport | None:
        stmt = select(InsightReport).order_by(InsightReport.id.desc()).limit(limit_scan)
        for report in self.session.scalars(stmt).all():
            if isinstance(report.facts, dict) and report.facts.get("facts_hash") == facts_hash:
                return report
        return None


def save_dataset(session: Session, payload: DatasetCreate) -> Dataset:
    return DatasetRepository(session).create_with_observations(payload)


def delete_dataset(session: Session, dataset_id: int) -> bool:
    return DatasetRepository(session).delete_by_id(dataset_id)
