# SentryMind — 3-Minute Demo Video Script

**Author:** Aum Namaha  
**Duration:** ~3:00 minutes  
**Recording Tool:** OBS Studio (screen capture + webcam optional)  
**App URL:** `http://localhost:8501` (Streamlit app)

---

## Pre-Recording Checklist

- [ ] Start Streamlit app: `streamlit run app.py`
- [ ] Open Hindsight Cloud dashboard in a second tab
- [ ] Verify seed data is loaded (3 incidents should appear in memory bank)
- [ ] Set OBS scene to capture the full browser window at 1080p
- [ ] Record 5 seconds of black screen before starting for editing headroom

---

## Section 1 — Intro: What Is SentryMind? (0:00 – 0:30)

**Visual:** Full-screen view of the Streamlit app homepage (no clicks yet).

> "Hey everyone, I'm Aum. Today I want to show you a tool I built called **SentryMind** — an autonomous DevOps incident response agent."
>
> "The problem it solves is simple but real: production LLM agents keep guessing the wrong fix for incidents they've already seen before. They have no memory of past post-mortems, so every alert triggers the same generic 'restart service' advice."
>
> "SentryMind fixes that by plugging a local Qwen 35B model into **Hindsight Cloud** — a persistent incident memory system. The agent can recall verified runbook fixes from past incidents and act on them with high confidence."

---

## Section 2 — The Failure Mode: Without Memory (0:30 – 1:00)

**Visual:** Click "PostgreSQL Connection Pool Exhausted" in the sidebar → click **"Analyze Log (Without Memory)"**.

> "Let me show you what happens without memory. I'm selecting a PostgreSQL connection pool exhaustion alert."
>
> [Click the left button]
>
> "And here's the agent's response: **'Standard generic triage: Restart service.'** That's dangerous advice — restarting a production database during a traffic spike can make things worse."
>
> "Confidence is marked as low. The agent has no idea what actually caused this."

---

## Section 3 — With Hindsight Memory (1:00 – 2:30)

**Visual:** Stay on the same incident → click **"Analyze Log (With Hindsight Recall)"**. Zoom in on the right column JSON output.

> "Now let me run the exact same log through SentryMind with Hindsight memory enabled."
>
> [Click the right button — wait for spinner to finish]
>
> "Big difference. The agent recalls a **verified runbook from past post-mortems**: 'Run scripts/flush_pool.sh to drain idle connections. DO NOT restart DB.'"
>
> "Confidence is marked as high because it's pulling from an actual resolved incident stored in the Hindsight bank. This isn't a guess — it's a proven fix."
>
> "The pipeline works like this: error log comes in → semantic search against the memory bank → matching post-mortem retrieved → LLM generates targeted action steps with confidence scoring."

---

## Section 4 — Real-Time Learning (2:30 – 3:00)

**Visual:** Scroll down to **"Retain New Incident Learnings"** section. Fill out the form and click "Store in Hindsight Memory".

> "And here's the killer feature — real-time learning. If we resolve a new incident, we can push it directly into memory."
>
> [Fill in: ID = INC-004, Error = 'Redis Connection Timeout on Port 6379', Root Cause = 'Stale DNS record on Auth Gateway', Fix = 'Run systemctl restart systemd-resolved']
>
> [Click "Store in Hindsight Memory"]
>
> "That incident is now stored. Next time a similar alert comes in, SentryMind will recall this fix automatically."
>
> "Building agents that remember — that's the difference between a demo and production tooling. Thanks for watching."

---

## YouTube Title Ideas (5 Options)

1. **"I Gave My DevOps Agent a Memory — Here's What Happened"**
2. **"Why LLMs Keep Guessing Wrong Fixes (And How to Fix It)"**
3. **"Building an AI Agent That Actually Remembers Production Incidents"**
4. **"SentryMind: Autonomous DevOps Agent With Persistent Memory"**
5. **"From Stateless Guesses to Verified Runbooks — AI Incident Response 2.0"**

---

## NanoBanana Thumbnail Image Prompt (16:9)

> **Prompt:** "A futuristic cybersecurity dashboard illustration in a cinematic dark-blue and electric-purple color palette. Center composition showing a glowing brain-shaped neural network icon made of circuit-board lines, with floating terminal windows displaying green code snippets and red alert badges around it. A shield emblem labeled 'SentryMind' sits at the bottom center. Style: modern tech vector art with subtle gradient lighting, clean negative space on the right side for text overlay. Aspect ratio 16:9, ultra-detailed, professional SaaS product aesthetic."
