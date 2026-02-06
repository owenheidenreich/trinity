"""
Phase 4 Tests: Experimentation Framework

Tests for:
- Experiment definitions and variant assignment
- Hash-based deterministic assignment
- A/B test middleware
- Parallel pipeline execution
"""


import pytest

# =============================================================================
# EXPERIMENT FRAMEWORK TESTS
# =============================================================================


class TestVariant:
    """Test Variant dataclass validation."""

    def test_valid_variant(self):
        """Valid variant should be created successfully."""
        from services.experiments import Variant

        variant = Variant("control", 0.5, {"mode": "legacy"})

        assert variant.name == "control"
        assert variant.weight == 0.5
        assert variant.config == {"mode": "legacy"}

    def test_variant_weight_bounds(self):
        """Variant weight must be between 0 and 1."""
        from services.experiments import Variant

        # Valid bounds
        Variant("low", 0.0, {})
        Variant("high", 1.0, {})

        # Invalid bounds
        with pytest.raises(ValueError, match="weight must be between"):
            Variant("negative", -0.1, {})

        with pytest.raises(ValueError, match="weight must be between"):
            Variant("over", 1.1, {})

    def test_variant_empty_name(self):
        """Variant name cannot be empty."""
        from services.experiments import Variant

        with pytest.raises(ValueError, match="name cannot be empty"):
            Variant("", 0.5, {})


class TestExperiment:
    """Test Experiment dataclass validation."""

    def test_valid_experiment(self):
        """Valid experiment should be created successfully."""
        from services.experiments import Experiment, Variant

        exp = Experiment(
            name="test_exp",
            description="Test experiment",
            variants=[Variant("A", 0.5, {}), Variant("B", 0.5, {})],
        )

        assert exp.name == "test_exp"
        assert exp.enabled is True
        assert len(exp.variants) == 2

    def test_experiment_weights_must_sum_to_one(self):
        """Experiment variant weights must sum to approximately 1.0."""
        from services.experiments import Experiment, Variant

        # Valid sum
        Experiment(
            name="valid",
            description="Valid",
            variants=[Variant("A", 0.5, {}), Variant("B", 0.5, {})],
        )

        # Invalid sum
        with pytest.raises(ValueError, match="weights must sum to 1.0"):
            Experiment(
                name="invalid",
                description="Invalid",
                variants=[Variant("A", 0.3, {}), Variant("B", 0.3, {})],
            )

    def test_experiment_empty_name(self):
        """Experiment name cannot be empty."""
        from services.experiments import Experiment, Variant

        with pytest.raises(ValueError, match="name cannot be empty"):
            Experiment(name="", description="Test", variants=[Variant("A", 1.0, {})])

    def test_experiment_must_have_variants(self):
        """Experiment must have at least one variant."""
        from services.experiments import Experiment

        with pytest.raises(ValueError, match="at least one variant"):
            Experiment(name="test", description="Test", variants=[])


class TestAssignVariant:
    """Test deterministic variant assignment."""

    def test_deterministic_assignment(self):
        """Same session should always get same variant."""
        from services.experiments import assign_variant

        session_id = "user-12345"

        # Multiple calls should return same variant
        variant1 = assign_variant("agent_mode", session_id)
        variant2 = assign_variant("agent_mode", session_id)
        variant3 = assign_variant("agent_mode", session_id)

        assert variant1.name == variant2.name == variant3.name

    def test_different_sessions_may_differ(self):
        """Different sessions should be distributed across variants."""
        from services.experiments import assign_variant

        # Test with many sessions to verify distribution
        variants_seen = set()
        for i in range(100):
            variant = assign_variant("agent_mode", f"session-{i}")
            if variant:
                variants_seen.add(variant.name)

        # Should see both variants with 100 samples
        assert len(variants_seen) >= 2

    def test_disabled_experiment_returns_none(self):
        """Disabled experiments should return None."""
        from services.experiments import assign_variant, disable_experiment, enable_experiment

        # Ensure experiment is disabled
        disable_experiment("parallel_execution")

        variant = assign_variant("parallel_execution", "any-session")
        assert variant is None

        # Re-enable for other tests
        enable_experiment("parallel_execution")

    def test_nonexistent_experiment_returns_none(self):
        """Non-existent experiments should return None."""
        from services.experiments import assign_variant

        variant = assign_variant("does_not_exist", "any-session")
        assert variant is None

    def test_hash_distribution_is_uniform(self):
        """Hash-based assignment should be roughly uniform."""
        # Enable the experiment for this test
        from services.experiments import assign_variant, enable_experiment

        enable_experiment("agent_mode")

        counts = {"control": 0, "langgraph": 0}
        sample_size = 1000

        for i in range(sample_size):
            variant = assign_variant("agent_mode", f"test-session-{i}")
            if variant:
                counts[variant.name] += 1

        # With 50/50 split, expect each around 500 (allow 15% variance)
        for name, count in counts.items():
            ratio = count / sample_size
            assert 0.35 < ratio < 0.65, f"Variant {name} ratio {ratio} outside expected range"


class TestListExperiments:
    """Test experiment listing functions."""

    def test_list_all_experiments(self):
        """Should list all defined experiments."""
        from services.experiments import list_experiments

        all_exps = list_experiments(enabled_only=False)

        assert "agent_mode" in all_exps
        assert "complexity_threshold" in all_exps
        assert "parallel_execution" in all_exps

    def test_list_enabled_only(self):
        """Should filter to only enabled experiments."""
        from services.experiments import disable_experiment, list_experiments

        # Disable one experiment
        disable_experiment("parallel_execution")

        enabled_exps = list_experiments(enabled_only=True)

        assert "parallel_execution" not in enabled_exps
        assert "agent_mode" in enabled_exps


class TestEnableDisable:
    """Test experiment enable/disable functions."""

    def test_enable_experiment(self):
        """Should enable a disabled experiment."""
        from services.experiments import disable_experiment, enable_experiment, get_experiment

        # First disable
        disable_experiment("reasoning_depth")
        assert get_experiment("reasoning_depth").enabled is False

        # Then enable
        result = enable_experiment("reasoning_depth")
        assert result is True
        assert get_experiment("reasoning_depth").enabled is True

    def test_disable_experiment(self):
        """Should disable an enabled experiment."""
        from services.experiments import disable_experiment, enable_experiment, get_experiment

        # First enable
        enable_experiment("reasoning_depth")
        assert get_experiment("reasoning_depth").enabled is True

        # Then disable
        result = disable_experiment("reasoning_depth")
        assert result is True
        assert get_experiment("reasoning_depth").enabled is False

    def test_enable_nonexistent_returns_false(self):
        """Enabling non-existent experiment returns False."""
        from services.experiments import enable_experiment

        result = enable_experiment("does_not_exist")
        assert result is False


class TestGetAllAssignments:
    """Test getting all assignments for a session."""

    def test_get_all_assignments(self):
        """Should return assignments for all enabled experiments."""
        from services.experiments import enable_experiment, get_all_assignments

        # Enable experiments
        enable_experiment("agent_mode")
        enable_experiment("complexity_threshold")
        enable_experiment("reasoning_depth")

        assignments = get_all_assignments("test-session-123")

        # Should have assignments for enabled experiments
        assert "agent_mode" in assignments
        assert "variant" in assignments["agent_mode"]
        assert "config" in assignments["agent_mode"]


# =============================================================================
# AB TEST MIDDLEWARE TESTS
# =============================================================================


class TestGetSessionId:
    """Test session ID extraction."""

    def test_session_id_from_principal_header(self):
        """Should prefer principal from header."""
        from flask import Flask
        from middleware.ab_test import get_session_id

        app = Flask(__name__)
        with app.test_request_context(headers={"X-ICP-Principal": "abc123"}):
            session_id = get_session_id()
            assert session_id == "principal:abc123"

    def test_session_id_from_session_header(self):
        """Should use X-Session-ID if no principal."""
        from flask import Flask
        from middleware.ab_test import get_session_id

        app = Flask(__name__)
        with app.test_request_context(headers={"X-Session-ID": "session-xyz"}):
            session_id = get_session_id()
            assert session_id == "session:session-xyz"

    def test_session_id_from_json_body(self):
        """Should use principal from JSON body."""
        from flask import Flask
        from middleware.ab_test import get_session_id

        app = Flask(__name__)
        with app.test_request_context(
            json={"principal": "body-principal"}, content_type="application/json"
        ):
            session_id = get_session_id()
            assert session_id == "principal:body-principal"

    def test_session_id_fallback_to_anon(self):
        """Should fallback to anonymous hash."""
        from flask import Flask
        from middleware.ab_test import get_session_id

        app = Flask(__name__)
        with app.test_request_context():
            session_id = get_session_id()
            assert session_id.startswith("anon:")


class TestExperimentDecorator:
    """Test the @experiment decorator."""

    def test_decorator_assigns_experiment(self):
        """Decorator should assign experiment to g.experiments."""
        from flask import Flask, g
        from middleware.ab_test import experiment

        app = Flask(__name__)

        @experiment("agent_mode")
        def test_handler():
            return g.experiments.get("agent_mode", {})

        with app.test_request_context(headers={"X-Session-ID": "test-session"}):
            result = test_handler()

            assert "variant" in result
            assert "config" in result

    def test_multiple_experiments_decorator(self):
        """@experiments decorator should assign multiple experiments."""
        from flask import Flask, g
        from middleware.ab_test import experiments

        app = Flask(__name__)

        @experiments("agent_mode", "complexity_threshold")
        def test_handler():
            return dict(g.experiments)

        with app.test_request_context(headers={"X-Session-ID": "test-session"}):
            result = test_handler()

            assert "agent_mode" in result
            assert "complexity_threshold" in result


class TestExperimentHelpers:
    """Test experiment access helper functions."""

    def test_get_experiment_config(self):
        """Should retrieve config value from assigned experiment."""
        from flask import Flask
        from middleware.ab_test import experiment, get_experiment_config

        app = Flask(__name__)

        @experiment("agent_mode")
        def test_handler():
            return get_experiment_config("agent_mode", "mode", "default")

        with app.test_request_context(headers={"X-Session-ID": "test"}):
            result = test_handler()
            # Should be either 'legacy' or 'langgraph' based on assignment
            assert result in ["legacy", "langgraph"]

    def test_get_variant_name(self):
        """Should return assigned variant name."""
        from flask import Flask
        from middleware.ab_test import experiment, get_variant_name

        app = Flask(__name__)

        @experiment("agent_mode")
        def test_handler():
            return get_variant_name("agent_mode")

        with app.test_request_context(headers={"X-Session-ID": "test"}):
            result = test_handler()
            assert result in ["control", "langgraph"]

    def test_is_in_variant(self):
        """Should check if in specific variant."""
        from flask import Flask
        from middleware.ab_test import experiment, get_variant_name, is_in_variant

        app = Flask(__name__)

        @experiment("agent_mode")
        def test_handler():
            variant = get_variant_name("agent_mode")
            return is_in_variant("agent_mode", variant)

        with app.test_request_context(headers={"X-Session-ID": "test"}):
            result = test_handler()
            assert result is True


# =============================================================================
# PARALLEL PIPELINE TESTS
# =============================================================================


class TestPipelineResult:
    """Test PipelineResult dataclass."""

    def test_successful_result(self):
        """Successful pipeline result should have correct fields."""
        from services.parallel import PipelineResult

        result = PipelineResult(
            pipeline="legacy",
            response="Test response",
            duration_seconds=1.5,
            success=True,
            metadata={"passes": 3},
        )

        assert result.pipeline == "legacy"
        assert result.success is True
        assert result.error is None

    def test_failed_result(self):
        """Failed pipeline result should capture error."""
        from services.parallel import PipelineResult

        result = PipelineResult(
            pipeline="langgraph",
            response="",
            duration_seconds=0.5,
            success=False,
            error="Timeout exceeded",
        )

        assert result.success is False
        assert result.error == "Timeout exceeded"


class TestParallelPipelineScoring:
    """Test response scoring heuristics."""

    def test_score_empty_response(self):
        """Empty response should score 0."""
        from services.parallel import ParallelAgentPipeline

        pipeline = ParallelAgentPipeline("http://localhost:11434", "test-model")
        score = pipeline._score_response("")

        assert score == 0.0

    def test_score_short_response(self):
        """Short response should have low score."""
        from services.parallel import ParallelAgentPipeline

        pipeline = ParallelAgentPipeline("http://localhost:11434", "test-model")
        score = pipeline._score_response("Yes")

        assert score < 1.0

    def test_score_code_block_bonus(self):
        """Response with code blocks should get bonus."""
        from services.parallel import ParallelAgentPipeline

        pipeline = ParallelAgentPipeline("http://localhost:11434", "test-model")

        without_code = "Here is the solution to your problem."
        with_code = "Here is the solution:\n```python\nprint('hello')\n```"

        score_without = pipeline._score_response(without_code)
        score_with = pipeline._score_response(with_code)

        assert score_with > score_without

    def test_score_list_formatting_bonus(self):
        """Response with lists should get bonus."""
        from services.parallel import ParallelAgentPipeline

        pipeline = ParallelAgentPipeline("http://localhost:11434", "test-model")

        plain = "First do this. Then do that."
        with_list = "Steps:\n- First do this\n- Then do that"

        score_plain = pipeline._score_response(plain)
        score_list = pipeline._score_response(with_list)

        assert score_list > score_plain

    def test_score_error_penalty(self):
        """Response starting with error indicators should get penalty."""
        from services.parallel import ParallelAgentPipeline

        pipeline = ParallelAgentPipeline("http://localhost:11434", "test-model")

        good = "Here is the answer you requested."
        bad = "Sorry, I cannot help with that request."

        score_good = pipeline._score_response(good)
        score_bad = pipeline._score_response(bad)

        assert score_good > score_bad


class TestParallelPipelineVoting:
    """Test voting logic between pipelines."""

    def test_vote_one_failed(self):
        """If one pipeline fails, other wins."""
        from services.parallel import ParallelAgentPipeline, PipelineResult

        pipeline = ParallelAgentPipeline("http://localhost:11434", "test-model")

        legacy = PipelineResult("legacy", "", 1.0, False, error="Failed")
        langgraph = PipelineResult("langgraph", "Success", 1.0, True)

        winner, confidence, reason = pipeline._vote(legacy, langgraph)

        assert winner == "langgraph"
        assert confidence == 1.0
        assert "failed" in reason.lower()

    def test_vote_both_failed(self):
        """If both fail, result is tie."""
        from services.parallel import ParallelAgentPipeline, PipelineResult

        pipeline = ParallelAgentPipeline("http://localhost:11434", "test-model")

        legacy = PipelineResult("legacy", "", 1.0, False, error="Failed")
        langgraph = PipelineResult("langgraph", "", 1.0, False, error="Also failed")

        winner, confidence, reason = pipeline._vote(legacy, langgraph)

        assert winner == "tie"
        assert confidence == 0.0

    def test_vote_similar_quality(self):
        """Similar quality responses should result in tie or speed-based winner."""
        from services.parallel import ParallelAgentPipeline, PipelineResult

        pipeline = ParallelAgentPipeline("http://localhost:11434", "test-model")

        legacy = PipelineResult("legacy", "Good response here", 1.0, True)
        langgraph = PipelineResult("langgraph", "Good response here", 1.5, True)

        winner, confidence, reason = pipeline._vote(legacy, langgraph)

        # Should be tie or legacy wins on speed
        assert winner in ["tie", "legacy"]


class TestParallelPipelineSingleton:
    """Test singleton pattern for parallel pipeline."""

    def test_get_parallel_pipeline_singleton(self):
        """Should return same instance."""
        from services.parallel import get_parallel_pipeline, reset_parallel_pipeline

        reset_parallel_pipeline()  # Start fresh

        pipeline1 = get_parallel_pipeline("http://localhost:11434", "test-model")
        pipeline2 = get_parallel_pipeline()

        assert pipeline1 is pipeline2

    def test_reset_parallel_pipeline(self):
        """Reset should clear singleton."""
        from services.parallel import get_parallel_pipeline, reset_parallel_pipeline

        pipeline1 = get_parallel_pipeline("http://localhost:11434", "test-model")
        reset_parallel_pipeline()
        pipeline2 = get_parallel_pipeline("http://localhost:11434", "test-model")

        assert pipeline1 is not pipeline2


# =============================================================================
# EXPERIMENT METRICS TESTS
# =============================================================================


class TestExperimentMetrics:
    """Test experiment metrics are defined."""

    def test_experiment_assignments_metric_exists(self):
        """EXPERIMENT_ASSIGNMENTS metric should exist."""
        from middleware.observability import EXPERIMENT_ASSIGNMENTS, PROMETHEUS_AVAILABLE

        if PROMETHEUS_AVAILABLE:
            assert EXPERIMENT_ASSIGNMENTS is not None

    def test_experiment_exposures_metric_exists(self):
        """EXPERIMENT_EXPOSURES metric should exist."""
        from middleware.observability import EXPERIMENT_EXPOSURES, PROMETHEUS_AVAILABLE

        if PROMETHEUS_AVAILABLE:
            assert EXPERIMENT_EXPOSURES is not None

    def test_parallel_executions_metric_exists(self):
        """PARALLEL_EXECUTIONS metric should exist."""
        from middleware.observability import PARALLEL_EXECUTIONS, PROMETHEUS_AVAILABLE

        if PROMETHEUS_AVAILABLE:
            assert PARALLEL_EXECUTIONS is not None


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestExperimentIntegration:
    """Integration tests for the full experiment flow."""

    def test_full_assignment_flow(self):
        """Test complete flow from session to variant config."""
        from services.experiments import assign_variant, enable_experiment

        # Enable experiment
        enable_experiment("agent_mode")

        # Assign variant
        variant = assign_variant("agent_mode", "integration-test-session")

        # Verify we got a valid variant
        assert variant is not None
        assert variant.name in ["control", "langgraph"]
        assert "mode" in variant.config

    def test_validate_distribution(self):
        """Use the built-in distribution validator."""
        from services.experiments import enable_experiment, validate_assignment_distribution

        enable_experiment("agent_mode")

        distribution = validate_assignment_distribution("agent_mode", sample_size=500)

        # Each variant should be roughly 50%
        for name, ratio in distribution.items():
            assert 0.3 < ratio < 0.7, f"{name} ratio {ratio} outside expected range"
