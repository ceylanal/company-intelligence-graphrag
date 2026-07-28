"""CLI interface for Company Intelligence Multi-Agent System."""

import argparse
import sys

from company_graphrag.agents.observability import AgentTracer
from company_graphrag.agents.workflow import JSONCheckpointSaver, ResearchWorkflow


def main():
    parser = argparse.ArgumentParser(
        description="Company Intelligence Multi-Agent System CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. start
    start_parser = subparsers.add_parser("start", help="Start a new multi-agent research workflow")
    start_parser.add_argument("query", type=str, help="Natural language research query string")

    # 2. status
    status_parser = subparsers.add_parser("status", help="Display workflow status for run_id")
    status_parser.add_argument("run_id", type=str, help="Workflow run_id string")

    # 3. resume
    resume_parser = subparsers.add_parser("resume", help="Resume an interrupted or paused workflow")
    resume_parser.add_argument("run_id", type=str, help="Workflow run_id string")

    # 4. show
    show_parser = subparsers.add_parser("show", help="Display synthesized final report answer")
    show_parser.add_argument("run_id", type=str, help="Workflow run_id string")

    # 5. citations
    cit_parser = subparsers.add_parser("citations", help="Inspect active citations and evidence appendix")
    cit_parser.add_argument("run_id", type=str, help="Workflow run_id string")

    # 6. trace
    trace_parser = subparsers.add_parser("trace", help="Render structured agent execution trace table")
    trace_parser.add_argument("run_id", type=str, help="Workflow run_id string")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    saver = JSONCheckpointSaver("data/checkpoints")
    tracer = AgentTracer()

    if args.command == "start":
        print(f"🚀 Starting multi-agent research workflow for query: '{args.query}'...\n")
        workflow = ResearchWorkflow(checkpoint_saver=saver, auto_approve_interrupts=True)
        state = workflow.run(args.query)

        print("✅ Workflow Execution Completed!")
        print(f"  run_id:          {state.run_id}")
        print(f"  Status:          {state.status.value if hasattr(state.status, 'value') else state.status}")
        print(f"  Completed Tasks: {state.completed_tasks}")
        print(f"  Evidence Count:  {len(state.evidence)}")
        print(f"  Verified Claims: {len(state.verified_claims)}")

        if state.final_answer:
            print("\n" + "=" * 60)
            print("📋 Final Synthesized Answer Preview:\n")
            print(state.final_answer[:500] + "...\n")
            print("Use 'python -m company_graphrag.cli.agent_cli show <run_id>' to read full report.")

    elif args.command == "status":
        state = saver.load_checkpoint(args.run_id)
        print(f"=== Workflow Status: run_id='{state.run_id}' ===")
        print(f"  User Query:      {state.user_query}")
        print(f"  Status:          {state.status}")
        print(f"  Current Stage:   {state.current_stage}")
        print(f"  Completed Tasks: {state.completed_tasks}")
        print(f"  Evidence Count:  {len(state.evidence)}")
        print(f"  Verified Claims: {len(state.verified_claims)}")
        print(f"  Contradictions:  {len(state.contradictions)}")

    elif args.command == "resume":
        print(f"🔄 Resuming workflow for run_id='{args.run_id}'...\n")
        workflow = ResearchWorkflow(checkpoint_saver=saver, auto_approve_interrupts=True)
        state = workflow.resume(args.run_id)
        print("✅ Workflow Resumed & Completed!")
        print(f"  Status:          {state.status}")
        print(f"  Completed Tasks: {state.completed_tasks}")

    elif args.command == "show":
        state = saver.load_checkpoint(args.run_id)
        if state.final_answer:
            print(f"=== Grounded Research Report: run_id='{state.run_id}' ===\n")
            print(state.final_answer)
        else:
            print(f"No final answer generated yet for run_id='{args.run_id}'. Status is {state.status}.")

    elif args.command == "citations":
        state = saver.load_checkpoint(args.run_id)
        print(f"=== Citations & Evidence Appendix: run_id='{state.run_id}' ===\n")
        if state.structured_report and state.structured_report.citations:
            for cit in state.structured_report.citations:
                print(
                    f"**[Source {cit.citation_index}]** {cit.company} ({cit.ticker}) - {cit.year} Raporu\n"
                    f"  - PDF File: {cit.source_file} (Page {cit.page_number}, Chunk ID: {cit.chunk_id})\n"
                    f"  - Snippet: \"{cit.snippet}\"\n"
                )
        else:
            print("No active citations found.")

    elif args.command == "trace":
        state = saver.load_checkpoint(args.run_id)

        # Build mock trace from state tool calls if tracer buffer is fresh
        if state.tool_calls:
            print(f"=== 🔍 Tool Call Audit Log: run_id='{state.run_id}' ===")
            print(f"{'Role':<20} | {'Tool':<18} | {'Latency':<8} | {'Status':<7} | {'Summary'}")
            print("-" * 80)
            for tc in state.tool_calls:
                st = "OK" if tc.success else "ERR"
                print(f"{tc.agent_role:<20} | {tc.tool_name:<18} | {tc.execution_time_ms:>6.1f}ms | {st:<7} | {tc.output_summary[:25]}")
            print("-" * 80)
        else:
            print(tracer.render_run_trace(args.run_id))


if __name__ == "__main__":
    main()
