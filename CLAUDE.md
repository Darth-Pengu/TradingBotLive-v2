\# ZMN Bot — Claude Code Session Rules



\## Read this first, every session

\- Read AGENT\_CONTEXT.md completely before writing any code

\- Check what already exists in services/ before building anything new

\- Never assume a file exists — always check first



\## API reference rule

\- Before fixing any API integration, check Section 21 of AGENT\_CONTEXT.md for verified URL and field name reference. Do not rely on training data for API details — they change frequently.


\## Non-negotiable rules

\- All Python is async/await — no sync blocking calls anywhere

\- Never hardcode API keys, private keys, or wallet addresses

\- TEST\_MODE=true means zero trades — not reduced, zero

\- MAX\_WALLET\_EXPOSURE is 0.25 (25%) — never exceed

\- Holding wallet address is read-only — private key never in code

\- Run python -c "import services.filename" before committing



\## Architecture

\- All services in services/ — no monolithic files

\- Services communicate only via Redis

\- Never import one service directly into another at module level



\## After every task

\- Run the file to check imports cleanly

\- Commit: "feat/fix: description"

\- Push to GitHub

\- Tell me what was built and what to test

