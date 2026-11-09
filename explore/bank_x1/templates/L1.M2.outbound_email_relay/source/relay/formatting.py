"""Message rendering helpers: build the header block and body of relayed messages.

{{UNRELATED_NOTE}}
"""


def header_block(sender: str, subject: str, ref: str) -> str:
    lines = [
        f"From: {sender}",
        "To: undisclosed-recipients:;",
        f"Subject: {subject.strip() or '(no subject)'}",
        f"X-Relay-Ref: {ref}",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
    ]
    return "\r\n".join(lines)


def render_message(request, ref: str) -> str:
    body = request.body.replace("\r\n", "\n").replace("\n", "\r\n")
    return header_block(request.sender, request.subject, ref) + "\r\n\r\n" + body
