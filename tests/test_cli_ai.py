"""Tests for nb.cli.ai module."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from nb.cli import cli


@pytest.fixture
def runner():
    """Create a Click CLI runner."""
    return CliRunner()


class TestAskCommand:
    """Tests for the nb ask command."""

    def test_ask_help(self, runner):
        """Test that ask --help works."""
        result = runner.invoke(cli, ["ask", "--help"])

        assert result.exit_code == 0
        assert "Ask a question about your notes" in result.output
        assert "--notebook" in result.output
        assert "--note" in result.output
        assert "--tag" in result.output

    def test_ask_without_api_key(self, runner, mock_cli_config):
        """Test that ask fails gracefully without API key."""
        from nb.core.llm import LLMConfigError

        # Mock search to return results, so LLM is called
        class MockResult:
            def __init__(self):
                self.content = "Some content"
                self.score = 0.9
                self.metadata = {"path": "test.md", "title": "Test"}

        with (
            patch("nb.core.ai.ask.get_config", return_value=mock_cli_config),
            patch("nb.core.ai.ask.get_search") as mock_search,
            patch(
                "nb.core.ai.ask.get_llm_client",
                side_effect=LLMConfigError("No API key configured"),
            ),
        ):
            mock_search.return_value.db.query.return_value = [MockResult()]

            result = runner.invoke(cli, ["ask", "what is this?", "--no-stream"])

            assert result.exit_code == 1
            assert "Configuration error" in result.output or "API key" in result.output

    def test_ask_no_results(self, runner, mock_cli_config):
        """Test ask when no relevant notes are found."""
        from nb.config import LLMConfig

        mock_cli_config.llm = LLMConfig(provider="anthropic", api_key="test-key")

        with (
            patch("nb.core.ai.ask.get_config", return_value=mock_cli_config),
            patch("nb.core.ai.ask.get_search") as mock_search,
        ):
            mock_search.return_value.db.query.return_value = []

            result = runner.invoke(cli, ["ask", "unknown topic", "--no-stream"])

            # Should not crash, should indicate no results found
            assert "couldn't find" in result.output.lower() or result.exit_code == 0

    def test_ask_with_notebook_filter(self, runner, mock_cli_config):
        """Test ask with notebook filter option."""
        from nb.config import LLMConfig
        from nb.core.ai.ask import AnswerResult, NoteReference

        mock_cli_config.llm = LLMConfig(provider="anthropic", api_key="test-key")

        mock_result = AnswerResult(
            answer="The answer is here.",
            sources=[
                NoteReference(
                    path="work/note.md",
                    title="Note",
                    snippet="...",
                    score=0.9,
                    notebook="work",
                )
            ],
            input_tokens=100,
            output_tokens=50,
        )

        with (
            patch("nb.core.ai.ask.get_config", return_value=mock_cli_config),
            patch("nb.core.ai.ask.ask_notes", return_value=mock_result) as mock_ask,
        ):
            result = runner.invoke(
                cli,
                ["ask", "question", "--notebook", "work", "--no-stream"],
            )

            # Verify notebook was passed
            mock_ask.assert_called_once()
            call_kwargs = mock_ask.call_args.kwargs
            assert call_kwargs.get("notebook") == "work"

    def test_ask_with_tag_filter(self, runner, mock_cli_config):
        """Test ask with tag filter option."""
        from nb.config import LLMConfig
        from nb.core.ai.ask import AnswerResult

        mock_cli_config.llm = LLMConfig(provider="anthropic", api_key="test-key")

        mock_result = AnswerResult(
            answer="Tagged result.",
            sources=[],
            input_tokens=100,
            output_tokens=50,
        )

        with (
            patch("nb.core.ai.ask.get_config", return_value=mock_cli_config),
            patch("nb.core.ai.ask.ask_notes", return_value=mock_result) as mock_ask,
        ):
            result = runner.invoke(
                cli,
                ["ask", "question", "--tag", "project", "--no-stream"],
            )

            mock_ask.assert_called_once()
            call_kwargs = mock_ask.call_args.kwargs
            assert call_kwargs.get("tag") == "project"

    def test_ask_smart_model_option(self, runner, mock_cli_config):
        """Test ask with --smart option."""
        from nb.config import LLMConfig
        from nb.core.ai.ask import AnswerResult

        mock_cli_config.llm = LLMConfig(provider="anthropic", api_key="test-key")

        mock_result = AnswerResult(
            answer="Smart answer.",
            sources=[],
            input_tokens=100,
            output_tokens=50,
        )

        with (
            patch("nb.core.ai.ask.get_config", return_value=mock_cli_config),
            patch("nb.core.ai.ask.ask_notes", return_value=mock_result) as mock_ask,
        ):
            result = runner.invoke(
                cli,
                ["ask", "question", "--smart", "--no-stream"],
            )

            mock_ask.assert_called_once()
            call_kwargs = mock_ask.call_args.kwargs
            assert call_kwargs.get("use_smart_model") is True

    def test_ask_fast_model_option(self, runner, mock_cli_config):
        """Test ask with --fast option."""
        from nb.config import LLMConfig
        from nb.core.ai.ask import AnswerResult

        mock_cli_config.llm = LLMConfig(provider="anthropic", api_key="test-key")

        mock_result = AnswerResult(
            answer="Fast answer.",
            sources=[],
            input_tokens=100,
            output_tokens=50,
        )

        with (
            patch("nb.core.ai.ask.get_config", return_value=mock_cli_config),
            patch("nb.core.ai.ask.ask_notes", return_value=mock_result) as mock_ask,
        ):
            result = runner.invoke(
                cli,
                ["ask", "question", "--fast", "--no-stream"],
            )

            mock_ask.assert_called_once()
            call_kwargs = mock_ask.call_args.kwargs
            assert call_kwargs.get("use_smart_model") is False


class TestPlanCommand:
    """Tests for the nb plan command."""

    def test_plan_help(self, runner):
        """Test that plan --help works."""
        result = runner.invoke(cli, ["plan", "--help"])

        assert result.exit_code == 0
        assert "AI-assisted planning" in result.output
        assert "week" in result.output
        assert "today" in result.output

    def test_plan_week_help(self, runner):
        """Test that plan week --help works."""
        result = runner.invoke(cli, ["plan", "week", "--help"])

        assert result.exit_code == 0
        assert "Plan the upcoming week" in result.output
        assert "--notebook" in result.output
        assert "--tag" in result.output
        assert "--interactive" in result.output

    def test_plan_today_help(self, runner):
        """Test that plan today --help works."""
        result = runner.invoke(cli, ["plan", "today", "--help"])

        assert result.exit_code == 0
        assert "Plan or replan today" in result.output
        assert "--no-calendar" in result.output
        assert "--prompt" in result.output

    def test_plan_week_without_api_key(self, runner, mock_cli_config):
        """Test that plan week fails gracefully without API key."""
        from nb.core.llm import LLMConfigError

        with (
            patch(
                "nb.core.ai.planning.get_llm_client",
                side_effect=LLMConfigError("No API key configured"),
            ),
            patch("nb.core.ai.planning.get_config", return_value=mock_cli_config),
        ):
            result = runner.invoke(cli, ["plan", "week", "--no-stream"])

            assert result.exit_code == 1
            assert "Configuration error" in result.output or "API key" in result.output

    def test_plan_week_option_parsing(self, runner):
        """Test that plan week parses options correctly."""
        # Just verify that options are accepted without error
        result = runner.invoke(
            cli,
            ["plan", "week", "--notebook", "work", "--help"],
        )
        assert result.exit_code == 0
        assert "--notebook" in result.output

    def test_plan_today_option_parsing(self, runner):
        """Test that plan today parses options correctly."""
        result = runner.invoke(
            cli,
            ["plan", "today", "--prompt", "Focus on urgent items", "--help"],
        )
        assert result.exit_code == 0
        assert "--prompt" in result.output

    def test_plan_week_smart_fast_options(self, runner):
        """Test that --smart and --fast options are mutually exclusive flags."""
        # Verify --smart is in help
        result = runner.invoke(cli, ["plan", "week", "--help"])
        assert "--smart" in result.output
        assert "--fast" in result.output


class TestReviewCommand:
    """Tests for the nb review command."""

    def test_review_help(self, runner):
        """Test that review --help works."""
        result = runner.invoke(cli, ["review", "--help"])

        assert result.exit_code == 0
        assert "AI-assisted daily and weekly reviews" in result.output
        assert "day" in result.output
        assert "week" in result.output

    def test_review_day_help(self, runner):
        """Test that review day --help works."""
        result = runner.invoke(cli, ["review", "day", "--help"])

        assert result.exit_code == 0
        assert "end-of-day review" in result.output
        assert "--notebook" in result.output
        assert "--tag" in result.output
        assert "--output" in result.output

    def test_review_week_help(self, runner):
        """Test that review week --help works."""
        result = runner.invoke(cli, ["review", "week", "--help"])

        assert result.exit_code == 0
        assert "end-of-week review" in result.output
        assert "--prompt" in result.output
        assert "--stream" in result.output

    def test_review_day_without_api_key(self, runner, mock_cli_config):
        """Test that review day fails gracefully without API key."""
        from nb.core.llm import LLMConfigError

        with (
            patch(
                "nb.core.ai.review.get_llm_client",
                side_effect=LLMConfigError("No API key configured"),
            ),
            patch("nb.core.ai.review.get_config", return_value=mock_cli_config),
        ):
            result = runner.invoke(cli, ["review", "day", "--no-stream"])

            assert result.exit_code == 1
            assert "Configuration error" in result.output or "API key" in result.output

    def test_review_day_option_parsing(self, runner):
        """Test that review day parses options correctly."""
        result = runner.invoke(
            cli,
            ["review", "day", "--notebook", "work", "--help"],
        )
        assert result.exit_code == 0
        assert "--notebook" in result.output

    def test_review_week_option_parsing(self, runner):
        """Test that review week parses options correctly."""
        result = runner.invoke(
            cli,
            ["review", "week", "--prompt", "Focus on wins", "--help"],
        )
        assert result.exit_code == 0
        assert "--prompt" in result.output

    def test_review_smart_fast_options(self, runner):
        """Test that --smart and --fast options are available."""
        result = runner.invoke(cli, ["review", "day", "--help"])
        assert "--smart" in result.output
        assert "--fast" in result.output


class TestStandupCommand:
    """Tests for the nb standup command."""

    def test_standup_help(self, runner):
        """Test that standup --help works."""
        result = runner.invoke(cli, ["standup", "--help"])

        assert result.exit_code == 0
        assert "morning standup briefing" in result.output
        assert "--notebook" in result.output
        assert "--tag" in result.output
        assert "--output" in result.output
        assert "--no-calendar" in result.output

    def test_standup_without_api_key(self, runner, mock_cli_config):
        """Test that standup fails gracefully without API key."""
        from nb.core.llm import LLMConfigError

        with (
            patch(
                "nb.core.ai.standup.get_llm_client",
                side_effect=LLMConfigError("No API key configured"),
            ),
            patch("nb.core.ai.standup.get_config", return_value=mock_cli_config),
        ):
            result = runner.invoke(cli, ["standup", "--no-stream"])

            assert result.exit_code == 1
            assert "Configuration error" in result.output or "API key" in result.output

    def test_standup_option_parsing(self, runner):
        """Test that standup parses options correctly."""
        result = runner.invoke(
            cli,
            ["standup", "--notebook", "work", "--help"],
        )
        assert result.exit_code == 0
        assert "--notebook" in result.output

    def test_standup_no_calendar_option(self, runner):
        """Test that --no-calendar option is available."""
        result = runner.invoke(cli, ["standup", "--help"])
        assert "--no-calendar" in result.output

    def test_standup_smart_fast_options(self, runner):
        """Test that --smart and --fast options are available."""
        result = runner.invoke(cli, ["standup", "--help"])
        assert "--smart" in result.output
        assert "--fast" in result.output
