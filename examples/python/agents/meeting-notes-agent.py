"""
Meeting Notes Agent

An AI meeting-notes pipeline composed entirely from existing PraisonAI
primitives — no new SDK surface required:

  1. AudioAgent.transcribe()  -> Whisper speech-to-text
  2. Agent (summary)          -> structured summary + action items
  3. Agent (knowledge=[...])  -> index transcript for cross-meeting Q&A

Usage:
    python meeting-notes-agent.py path/to/recording.mp3

Requires: OPENAI_API_KEY (or any LiteLLM-supported STT/LLM provider).
"""

import sys
from praisonaiagents import Agent, AudioAgent


def transcribe_meeting(audio_path: str) -> str:
    """Speech-to-text using the built-in Whisper AudioAgent."""
    stt = AudioAgent(llm="openai/whisper-1")
    return stt.transcribe(audio_path)


def summarize_meeting(transcript: str) -> str:
    """Summarize decisions, topics, and action items."""
    notetaker = Agent(
        name="Meeting Notetaker",
        instructions=(
            "You are an expert meeting notetaker. Given a raw transcript, produce:\n"
            "1. A concise summary (3-5 sentences).\n"
            "2. Key decisions made.\n"
            "3. Action items as a checklist with owners when mentioned.\n"
            "Only include action items that were actually spoken."
        ),
    )
    return notetaker.start(f"Transcript:\n\n{transcript}")


def build_qa_agent(transcript_path: str) -> Agent:
    """Index the transcript for semantic search and cross-meeting Q&A."""
    return Agent(
        name="Meeting Q&A",
        instructions="Answer questions using only the indexed meeting transcripts. Cite what was said.",
        knowledge=[transcript_path],
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python meeting-notes-agent.py <audio_file>")
        sys.exit(1)

    audio_path = sys.argv[1]

    transcript = transcribe_meeting(audio_path)
    transcript_path = "meeting_transcript.txt"
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript)

    notes = summarize_meeting(transcript)
    print("\n=== Meeting Notes ===\n")
    print(notes)

    qa = build_qa_agent(transcript_path)
    print("\n=== Q&A ===\n")
    print(qa.start("What were the main action items and who owns them?"))


if __name__ == "__main__":
    main()
