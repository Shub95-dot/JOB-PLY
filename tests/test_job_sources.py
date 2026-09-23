"""Unit tests for all 25+ UK and worldwide job sources in src/jobs/job_sources.py."""

import pytest
from src.core.models import Job
from src.jobs.job_sources import (
    LinkedInJobSource,
    IndeedJobSource,
    ReedJobSource,
    TotalJobsJobSource,
    CVLibraryJobSource,
    AIJobsNetJobSource,
    OuterJoinJobSource,
    RemoteOKJobSource,
    WeWorkRemotelyJobSource,
    HimalayasJobSource,
    RemoteCoJobSource,
    WellfoundJobSource,
    BuiltInRemoteJobSource,
    RemoteJobsLibraryJobSource,
    GlobalRemotelyJobSource,
    IndeedUKHybridJobSource,
    ReedUKHybridJobSource,
    TotalJobsHybridJobSource,
    CVLibraryHybridJobSource,
    CWJobsJobSource,
    TechnojobsJobSource,
    DataScienceJobsUKJobSource,
    JobsAcUkJobSource,
    IndeedUKOnsiteJobSource,
    ReedUKOnsiteJobSource,
    TotalJobsOnsiteJobSource,
    CVLibraryOnsiteJobSource,
    JoobleUKJobSource,
    AdzunaUKJobSource,
    DataScienceJobsUKOnsiteJobSource,
    RemotiveJobSource,
    RSSJobSource,
    MockJobSource,
    get_job_source,
)


def test_mock_job_source():
    source = MockJobSource()
    jobs = source.fetch_jobs()
    assert isinstance(jobs, list)
    assert len(jobs) > 0
    assert isinstance(jobs[0], Job)


@pytest.mark.parametrize("source_cls,expected_type", [
    (AIJobsNetJobSource, "Remote"),
    (OuterJoinJobSource, "Remote"),
    (RemoteOKJobSource, "Remote"),
    (HimalayasJobSource, "Remote"),
    (RemoteCoJobSource, "Remote"),
    (WellfoundJobSource, "Remote"),
    (BuiltInRemoteJobSource, "Remote"),
    (RemoteJobsLibraryJobSource, "Remote"),
    (GlobalRemotelyJobSource, "Remote"),
])
def test_remote_sources_structure(source_cls, expected_type):
    src = source_cls()
    jobs = src.fetch_jobs()
    assert isinstance(jobs, list)
    if jobs:
        assert isinstance(jobs[0], Job)
        assert jobs[0].work_type == expected_type


@pytest.mark.parametrize("source_cls,expected_type", [
    (IndeedUKHybridJobSource, "Hybrid"),
    (ReedUKHybridJobSource, "Hybrid"),
    (TotalJobsHybridJobSource, "Hybrid"),
    (CVLibraryHybridJobSource, "Hybrid"),
    (CWJobsJobSource, "Hybrid"),
    (TechnojobsJobSource, "Hybrid"),
    (DataScienceJobsUKJobSource, "Hybrid"),
    (JobsAcUkJobSource, "Hybrid"),
])
def test_hybrid_uk_sources_structure(source_cls, expected_type):
    src = source_cls()
    jobs = src.fetch_jobs()
    assert isinstance(jobs, list)
    if jobs:
        assert isinstance(jobs[0], Job)
        assert jobs[0].work_type == expected_type


@pytest.mark.parametrize("source_cls,expected_type", [
    (IndeedUKOnsiteJobSource, "On-site"),
    (ReedUKOnsiteJobSource, "On-site"),
    (TotalJobsOnsiteJobSource, "On-site"),
    (CVLibraryOnsiteJobSource, "On-site"),
    (JoobleUKJobSource, "On-site"),
    (AdzunaUKJobSource, "On-site"),
    (DataScienceJobsUKOnsiteJobSource, "On-site"),
])
def test_onsite_uk_sources_structure(source_cls, expected_type):
    src = source_cls()
    jobs = src.fetch_jobs()
    assert isinstance(jobs, list)
    if jobs:
        assert isinstance(jobs[0], Job)
        assert jobs[0].work_type == expected_type


@pytest.mark.parametrize("group_name", [
    "remote_all", "hybrid_uk", "onsite_uk", "all"
])
def test_grouped_job_sources_factory(group_name):
    source = get_job_source(group_name)
    assert source is not None
    assert hasattr(source, "fetch_jobs")
    jobs = source.fetch_jobs()
    assert isinstance(jobs, list)
