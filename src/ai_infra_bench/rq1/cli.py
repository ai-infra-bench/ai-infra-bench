"""Command-line entry point for RQ1 data preparation and labeling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_infra_bench.rq1.coverage import event_coverage
from ai_infra_bench.rq1.event_snapshot import download_snapshot
from ai_infra_bench.rq1.git_manifest import iter_merged_prs, write_manifest
from ai_infra_bench.rq1.github_issue_details import collect_issue_details
from ai_infra_bench.rq1.github_pr_details import (
    RotatingGraphQLClient,
    collect_pr_commits,
    collect_pr_details,
    collect_pr_responses,
    github_tokens_from_environment,
)
from ai_infra_bench.rq1.github_rest import (
    GitHubRestClient,
    collect_rest_base_snapshot,
)
from ai_infra_bench.rq1.github_review_comments import (
    GitHubReviewCommentClient,
    collect_review_comments,
)
from ai_infra_bench.rq1.github_snapshot import (
    GitHubGraphQLClient,
    collect_base_snapshot,
    github_token_from_environment,
)
from ai_infra_bench.rq1.issue_metrics import (
    derive_issue_metrics,
    write_issue_metrics,
)
from ai_infra_bench.rq1.label_findings import (
    summarize_labels,
    write_label_summary,
)
from ai_infra_bench.rq1.model_labeler import (
    LabelingConfig,
    ModelLabeler,
    api_keys_from_environment,
    public_config,
)
from ai_infra_bench.rq1.pr_lifecycle import (
    derive_pr_lifecycle,
    write_pr_lifecycle,
)
from ai_infra_bench.rq1.pr_manifest import merge_pr_manifests
from ai_infra_bench.rq1.pr_response_metrics import (
    derive_pr_response_metrics,
    write_pr_response_metrics,
)
from ai_infra_bench.rq1.pr_review_metrics import (
    derive_pr_review_metrics,
    write_pr_review_metrics,
)
from ai_infra_bench.rq1.release_issue_metrics import (
    derive_release_issue_metrics,
)
from ai_infra_bench.rq1.release_label_alignment import (
    align_release_labels,
    build_missing_release_label_manifest,
    write_release_label_alignment,
    write_release_label_manifest,
)
from ai_infra_bench.rq1.sampling import backend_sample_jsonl, sample_jsonl


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aib-rq1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest = subparsers.add_parser(
        "git-manifest",
        help="build the merged-PR bootstrap manifest from local Git history",
    )
    manifest.add_argument("--repository", type=Path, required=True)
    manifest.add_argument("--cutoff", default="2026-08-08T23:59:59Z")
    manifest.add_argument("--output", type=Path, required=True)

    sample = subparsers.add_parser(
        "sample", help="draw a deterministic period-by-patch-size sample"
    )
    sample.add_argument("--input", type=Path, required=True)
    sample.add_argument("--output", type=Path, required=True)
    sample.add_argument("--count", type=int, required=True)
    sample.add_argument("--seed", type=int, default=20260808)

    backend_sample = subparsers.add_parser(
        "backend-sample",
        help="oversample backend keywords for taxonomy validation",
    )
    backend_sample.add_argument("--input", type=Path, required=True)
    backend_sample.add_argument("--output", type=Path, required=True)
    backend_sample.add_argument("--per-backend", type=int, default=10)
    backend_sample.add_argument("--seed", type=int, default=20260808)

    events = subparsers.add_parser(
        "events-snapshot",
        help="download the frozen public-event supplement",
    )
    events.add_argument("--repository", default="vllm-project/vllm")
    events.add_argument("--cutoff", default="2026-08-08T23:59:59Z")
    events.add_argument("--output", type=Path, required=True)

    coverage = subparsers.add_parser(
        "event-coverage",
        help="measure public-event coverage against merged Git history",
    )
    coverage.add_argument("--events", type=Path, required=True)
    coverage.add_argument("--merged-manifest", type=Path, required=True)

    github = subparsers.add_parser(
        "github-base-snapshot",
        help="collect complete issue and PR base objects from GitHub GraphQL",
    )
    github.add_argument("--repository", default="vllm-project/vllm")
    github.add_argument("--cutoff", default="2026-08-08T23:59:59Z")
    github.add_argument("--output-dir", type=Path, required=True)

    github_rest = subparsers.add_parser(
        "github-rest-snapshot",
        help="efficiently collect the complete issue and PR census",
    )
    github_rest.add_argument("--repository", default="vllm-project/vllm")
    github_rest.add_argument("--cutoff", default="2026-08-08T23:59:59Z")
    github_rest.add_argument("--output-dir", type=Path, required=True)

    pr_manifest = subparsers.add_parser(
        "merge-pr-manifest",
        help="join GitHub PR metadata with default-branch Git evidence",
    )
    pr_manifest.add_argument("--github-prs", type=Path, required=True)
    pr_manifest.add_argument("--git-merged-prs", type=Path, required=True)
    pr_manifest.add_argument("--output", type=Path, required=True)
    pr_manifest.add_argument("--cutoff", default="2026-08-08T23:59:59Z")

    label = subparsers.add_parser(
        "label",
        help="label PR subsystem and accelerator scope with the configured model",
    )
    label.add_argument("--input", type=Path, required=True)
    label.add_argument("--output", type=Path, required=True)
    label.add_argument("--model", default="gpt-5.6-sol")
    label.add_argument("--batch-size", type=int, default=8)
    label.add_argument("--concurrency-per-key", type=int, default=1)
    label.add_argument("--limit", type=int)

    config = subparsers.add_parser(
        "label-config", help="print the public, secret-free labeling contract"
    )
    config.add_argument("--model", default="gpt-5.6-sol")

    findings = subparsers.add_parser(
        "summarize-labels",
        help="aggregate frozen PR subsystem and accelerator labels",
    )
    findings.add_argument("--labels", type=Path, required=True)
    findings.add_argument("--manifest", type=Path, required=True)
    findings.add_argument("--github-prs", type=Path, required=True)
    findings.add_argument("--output", type=Path, required=True)
    findings.add_argument("--cutoff", default="2026-08-08T23:59:59Z")

    lifecycle = subparsers.add_parser(
        "derive-pr-lifecycle",
        help="derive cutoff-aware per-PR merge, close, and censoring metrics",
    )
    lifecycle.add_argument("--labels", type=Path, required=True)
    lifecycle.add_argument("--manifest", type=Path, required=True)
    lifecycle.add_argument("--github-prs", type=Path, required=True)
    lifecycle.add_argument("--records-output", type=Path, required=True)
    lifecycle.add_argument("--summary-output", type=Path, required=True)
    lifecycle.add_argument("--cutoff", default="2026-08-08T23:59:59Z")

    details = subparsers.add_parser(
        "github-pr-details",
        help="collect resumable PR comments, reviews, commits, and threads",
    )
    details.add_argument("--input", type=Path, required=True)
    details.add_argument("--output-dir", type=Path, required=True)
    details.add_argument("--batch-size", type=int, default=10)
    details.add_argument("--concurrency", type=int, default=8)
    details.add_argument("--cutoff", default="2026-08-08T23:59:59Z")

    responses = subparsers.add_parser(
        "github-pr-responses",
        help="collect the lower-cost PR conversation comment and review layer",
    )
    responses.add_argument("--input", type=Path, required=True)
    responses.add_argument("--output-dir", type=Path, required=True)
    responses.add_argument("--batch-size", type=int, default=10)
    responses.add_argument("--concurrency", type=int, default=8)
    responses.add_argument("--cutoff", default="2026-08-08T23:59:59Z")

    response_metrics = subparsers.add_parser(
        "derive-pr-responses",
        help="derive per-PR first comment, maintainer response, and review times",
    )
    response_metrics.add_argument("--responses", type=Path, required=True)
    response_metrics.add_argument("--github-prs", type=Path, required=True)
    response_metrics.add_argument("--labels", type=Path, required=True)
    response_metrics.add_argument("--records-output", type=Path, required=True)
    response_metrics.add_argument("--summary-output", type=Path, required=True)
    response_metrics.add_argument(
        "--cutoff", default="2026-08-08T23:59:59Z"
    )

    issue_details = subparsers.add_parser(
        "github-issue-details",
        help="collect resumable issue comments and close/reopen timeline events",
    )
    issue_details.add_argument("--input", type=Path, required=True)
    issue_details.add_argument("--output-dir", type=Path, required=True)
    issue_details.add_argument("--batch-size", type=int, default=10)
    issue_details.add_argument("--concurrency", type=int, default=8)
    issue_details.add_argument(
        "--cutoff", default="2026-08-08T23:59:59Z"
    )

    issue_metrics = subparsers.add_parser(
        "derive-issue-metrics",
        help="derive issue arrivals, closures, backlog, and response metrics",
    )
    issue_metrics.add_argument("--details", type=Path, required=True)
    issue_metrics.add_argument("--github-issues", type=Path, required=True)
    issue_metrics.add_argument("--records-output", type=Path, required=True)
    issue_metrics.add_argument("--summary-output", type=Path, required=True)
    issue_metrics.add_argument(
        "--cutoff", default="2026-08-08T23:59:59Z"
    )

    release_issue_metrics = subparsers.add_parser(
        "derive-release-issue-metrics",
        help="derive issue metrics from the canonical release SQLite database",
    )
    release_issue_metrics.add_argument("--database", type=Path, required=True)
    release_issue_metrics.add_argument(
        "--records-output", type=Path, required=True
    )
    release_issue_metrics.add_argument(
        "--summary-output", type=Path, required=True
    )
    release_issue_metrics.add_argument("--cutoff")

    release_labels = subparsers.add_parser(
        "align-release-labels",
        help="map model PR labels onto the canonical release population",
    )
    release_labels.add_argument("--database", type=Path, required=True)
    release_labels.add_argument(
        "--labels", type=Path, action="append", required=True
    )
    release_labels.add_argument("--records-output", type=Path, required=True)
    release_labels.add_argument("--summary-output", type=Path, required=True)
    release_labels.add_argument(
        "--label-source-cutoff", action="append"
    )

    release_label_manifest = subparsers.add_parser(
        "build-release-label-manifest",
        help="build model inputs for canonical Release PRs without labels",
    )
    release_label_manifest.add_argument("--database", type=Path, required=True)
    release_label_manifest.add_argument(
        "--labels", type=Path, action="append", required=True
    )
    release_label_manifest.add_argument("--output", type=Path, required=True)
    release_label_manifest.add_argument(
        "--summary-output", type=Path, required=True
    )

    commits = subparsers.add_parser(
        "github-pr-commits",
        help="collect the low-cost PR commit timing layer",
    )
    commits.add_argument("--input", type=Path, required=True)
    commits.add_argument("--output-dir", type=Path, required=True)
    commits.add_argument("--batch-size", type=int, default=10)
    commits.add_argument("--concurrency", type=int, default=8)
    commits.add_argument("--cutoff", default="2026-08-08T23:59:59Z")

    review_comments = subparsers.add_parser(
        "github-review-comments",
        help="collect repository-wide line-level PR review comments",
    )
    review_comments.add_argument("--repository", default="vllm-project/vllm")
    review_comments.add_argument("--output-dir", type=Path, required=True)
    review_comments.add_argument("--concurrency", type=int, default=16)
    review_comments.add_argument("--cutoff", default="2026-08-08T23:59:59Z")

    review_metrics = subparsers.add_parser(
        "derive-pr-reviews",
        help="derive review counts, reviewers, comments, and round proxies",
    )
    review_metrics.add_argument("--responses", type=Path, required=True)
    review_metrics.add_argument("--commits", type=Path, required=True)
    review_metrics.add_argument("--review-comments", type=Path, required=True)
    review_metrics.add_argument("--github-prs", type=Path, required=True)
    review_metrics.add_argument("--labels", type=Path, required=True)
    review_metrics.add_argument("--records-output", type=Path, required=True)
    review_metrics.add_argument("--summary-output", type=Path, required=True)
    return parser


def main() -> None:
    """Run the selected RQ1 command."""
    args = _parser().parse_args()
    if args.command == "git-manifest":
        count = write_manifest(
            iter_merged_prs(args.repository, cutoff=args.cutoff),
            args.output,
        )
        print(json.dumps({"records": count, "output": str(args.output)}))
        return
    if args.command == "label-config":
        print(
            json.dumps(
                public_config(LabelingConfig(requested_model=args.model)),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if args.command == "sample":
        count = sample_jsonl(
            args.input,
            args.output,
            count=args.count,
            seed=args.seed,
        )
        print(json.dumps({"records": count, "output": str(args.output)}))
        return
    if args.command == "backend-sample":
        count = backend_sample_jsonl(
            args.input,
            args.output,
            per_backend=args.per_backend,
            seed=args.seed,
        )
        print(json.dumps({"records": count, "output": str(args.output)}))
        return
    if args.command == "events-snapshot":
        manifest = download_snapshot(
            args.output,
            repository=args.repository,
            cutoff=args.cutoff,
        )
        print(json.dumps(manifest, sort_keys=True))
        return
    if args.command == "event-coverage":
        print(
            json.dumps(
                event_coverage(args.events, args.merged_manifest),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if args.command == "github-base-snapshot":
        token = github_token_from_environment()
        if not token:
            raise SystemExit("set GITHUB_TOKEN or GH_TOKEN in the environment")
        manifest = collect_base_snapshot(
            args.output_dir,
            repository=args.repository,
            cutoff=args.cutoff,
            client=GitHubGraphQLClient(token),
        )
        print(json.dumps(manifest, sort_keys=True))
        return
    if args.command == "github-rest-snapshot":
        token = github_token_from_environment()
        if not token:
            raise SystemExit("set GITHUB_TOKEN or GH_TOKEN in the environment")
        manifest = collect_rest_base_snapshot(
            args.output_dir,
            repository=args.repository,
            cutoff=args.cutoff,
            client=GitHubRestClient(token),
        )
        print(json.dumps(manifest, sort_keys=True))
        return
    if args.command == "merge-pr-manifest":
        counts = merge_pr_manifests(
            args.github_prs,
            args.git_merged_prs,
            args.output,
            cutoff=args.cutoff,
        )
        print(json.dumps(counts, sort_keys=True))
        return
    if args.command == "summarize-labels":
        summary = summarize_labels(
            args.labels,
            args.manifest,
            args.github_prs,
            cutoff=args.cutoff,
        )
        write_label_summary(summary, args.output)
        print(
            json.dumps(
                {
                    "human_prs": summary["population"]["human_prs"],
                    "output": str(args.output),
                },
                sort_keys=True,
            )
        )
        return
    if args.command == "derive-pr-lifecycle":
        records, summary = derive_pr_lifecycle(
            args.labels,
            args.manifest,
            args.github_prs,
            cutoff=args.cutoff,
        )
        write_pr_lifecycle(
            records,
            summary,
            records_output=args.records_output,
            summary_output=args.summary_output,
        )
        print(
            json.dumps(
                {
                    "human_prs": summary["population"]["human_prs"],
                    "records": len(records),
                    "records_output": str(args.records_output),
                    "summary_output": str(args.summary_output),
                },
                sort_keys=True,
            )
        )
        return
    if args.command == "github-pr-details":
        tokens = github_tokens_from_environment()
        if not tokens:
            raise SystemExit(
                "set GITHUB_TOKENS, GITHUB_TOKEN, or GH_TOKEN in the environment"
            )
        manifest = collect_pr_details(
            args.input,
            args.output_dir,
            cutoff=args.cutoff,
            client=RotatingGraphQLClient(tokens),
            batch_size=args.batch_size,
            concurrency=args.concurrency,
        )
        print(json.dumps(manifest, sort_keys=True))
        return
    if args.command == "github-pr-responses":
        tokens = github_tokens_from_environment()
        if not tokens:
            raise SystemExit(
                "set GITHUB_TOKENS, GITHUB_TOKEN, or GH_TOKEN in the environment"
            )
        manifest = collect_pr_responses(
            args.input,
            args.output_dir,
            cutoff=args.cutoff,
            client=RotatingGraphQLClient(tokens),
            batch_size=args.batch_size,
            concurrency=args.concurrency,
        )
        print(json.dumps(manifest, sort_keys=True))
        return
    if args.command == "derive-pr-responses":
        records, summary = derive_pr_response_metrics(
            args.responses,
            args.github_prs,
            args.labels,
            cutoff=args.cutoff,
        )
        write_pr_response_metrics(
            records,
            summary,
            records_output=args.records_output,
            summary_output=args.summary_output,
        )
        print(
            json.dumps(
                {
                    "human_prs": summary["population"]["human_prs"],
                    "records": len(records),
                    "records_output": str(args.records_output),
                    "summary_output": str(args.summary_output),
                },
                sort_keys=True,
            )
        )
        return
    if args.command == "github-issue-details":
        tokens = github_tokens_from_environment()
        if not tokens:
            raise SystemExit(
                "set GITHUB_TOKENS, GITHUB_TOKEN, or GH_TOKEN in the environment"
            )
        manifest = collect_issue_details(
            args.input,
            args.output_dir,
            cutoff=args.cutoff,
            client=RotatingGraphQLClient(tokens),
            batch_size=args.batch_size,
            concurrency=args.concurrency,
        )
        print(json.dumps(manifest, sort_keys=True))
        return
    if args.command == "derive-issue-metrics":
        records, summary = derive_issue_metrics(
            args.details,
            args.github_issues,
            cutoff=args.cutoff,
        )
        write_issue_metrics(
            records,
            summary,
            records_output=args.records_output,
            summary_output=args.summary_output,
        )
        print(
            json.dumps(
                {
                    "human_issues": summary["population"]["human_issues"],
                    "records": len(records),
                    "records_output": str(args.records_output),
                    "summary_output": str(args.summary_output),
                },
                sort_keys=True,
            )
        )
        return
    if args.command == "derive-release-issue-metrics":
        records, summary = derive_release_issue_metrics(
            args.database,
            cutoff=args.cutoff,
        )
        write_issue_metrics(
            records,
            summary,
            records_output=args.records_output,
            summary_output=args.summary_output,
        )
        print(
            json.dumps(
                {
                    "human_issues": summary["population"]["human_issues"],
                    "records": len(records),
                    "records_output": str(args.records_output),
                    "summary_output": str(args.summary_output),
                },
                sort_keys=True,
            )
        )
        return
    if args.command == "align-release-labels":
        label_source_cutoffs = args.label_source_cutoff or [
            "2026-08-08T23:59:59Z"
        ]
        records, summary = align_release_labels(
            args.database,
            args.labels,
            label_source_cutoff=label_source_cutoffs,
        )
        write_release_label_alignment(
            records,
            summary,
            records_output=args.records_output,
            summary_output=args.summary_output,
        )
        print(
            json.dumps(
                {
                    "release_prs": summary["coverage"]["release_prs"],
                    "labeled": summary["coverage"]["release_prs_labeled"],
                    "missing": summary["coverage"][
                        "release_prs_missing_labels"
                    ],
                    "records_output": str(args.records_output),
                    "summary_output": str(args.summary_output),
                },
                sort_keys=True,
            )
        )
        return
    if args.command == "build-release-label-manifest":
        records, summary = build_missing_release_label_manifest(
            args.database,
            args.labels,
        )
        write_release_label_manifest(
            records,
            summary,
            output=args.output,
            summary_output=args.summary_output,
        )
        print(
            json.dumps(
                {
                    "records": len(records),
                    "with_file_paths": summary["records_with_file_paths"],
                    "without_file_paths": summary[
                        "records_without_file_paths"
                    ],
                    "output": str(args.output),
                },
                sort_keys=True,
            )
        )
        return
    if args.command == "github-pr-commits":
        tokens = github_tokens_from_environment()
        if not tokens:
            raise SystemExit(
                "set GITHUB_TOKENS, GITHUB_TOKEN, or GH_TOKEN in the environment"
            )
        manifest = collect_pr_commits(
            args.input,
            args.output_dir,
            cutoff=args.cutoff,
            client=RotatingGraphQLClient(tokens),
            batch_size=args.batch_size,
            concurrency=args.concurrency,
        )
        print(json.dumps(manifest, sort_keys=True))
        return
    if args.command == "github-review-comments":
        tokens = github_tokens_from_environment()
        if not tokens:
            raise SystemExit(
                "set GITHUB_TOKENS, GITHUB_TOKEN, or GH_TOKEN in the environment"
            )
        manifest = collect_review_comments(
            args.output_dir,
            repository=args.repository,
            cutoff=args.cutoff,
            client=GitHubReviewCommentClient(tokens[0]),
            concurrency=args.concurrency,
        )
        print(json.dumps(manifest, sort_keys=True))
        return
    if args.command == "derive-pr-reviews":
        records, summary = derive_pr_review_metrics(
            args.responses,
            args.commits,
            args.review_comments,
            args.github_prs,
            args.labels,
        )
        write_pr_review_metrics(
            records,
            summary,
            records_output=args.records_output,
            summary_output=args.summary_output,
        )
        print(
            json.dumps(
                {
                    "human_prs": summary["population"]["human_prs"],
                    "records": len(records),
                    "records_output": str(args.records_output),
                    "summary_output": str(args.summary_output),
                },
                sort_keys=True,
            )
        )
        return

    keys = api_keys_from_environment()
    if not keys:
        raise SystemExit(
            "AIB_MODEL_API_KEYS must contain one or more comma-separated keys"
        )
    config = LabelingConfig(
        requested_model=args.model,
        batch_size=args.batch_size,
        concurrency_per_key=args.concurrency_per_key,
    )
    written, total = ModelLabeler(keys, config).label_file(
        args.input,
        args.output,
        limit=args.limit,
    )
    print(json.dumps({"written": written, "total": total}))


if __name__ == "__main__":
    main()
