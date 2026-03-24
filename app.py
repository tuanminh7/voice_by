import os
import re
import uuid
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, session, stream_with_context

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - handled at runtime
    genai = None


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_PATH = BASE_DIR / "chatbot.txt"
MAX_HISTORY_ITEMS = 8
MAX_CONTEXT_CHUNKS = 6

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
app.json.ensure_ascii = False

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

model = None
if genai and API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)

knowledge = KNOWLEDGE_PATH.read_text(encoding="utf-8") if KNOWLEDGE_PATH.exists() else ""
knowledge_chunks = [line.strip() for line in knowledge.splitlines() if line.strip()]
chat_store = defaultdict(list)


def get_session_id() -> str:
    chat_session_id = session.get("chat_session_id")
    if not chat_session_id:
        chat_session_id = str(uuid.uuid4())
        session["chat_session_id"] = chat_session_id
    return chat_session_id


def extract_keywords(text: str) -> list[str]:
    words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    return [word for word in words if len(word) > 1]


def search_context(question: str) -> str:
    if not knowledge_chunks:
        return ""

    keywords = extract_keywords(question)
    if not keywords:
        return "\n".join(knowledge_chunks[:MAX_CONTEXT_CHUNKS])

    scored_chunks = []
    for chunk in knowledge_chunks:
        lowered_chunk = chunk.lower()
        score = sum(1 for keyword in keywords if keyword in lowered_chunk)
        if score:
            scored_chunks.append((score, chunk))

    if not scored_chunks:
        return "\n".join(knowledge_chunks[:MAX_CONTEXT_CHUNKS])

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    top_chunks = [chunk for _, chunk in scored_chunks[:MAX_CONTEXT_CHUNKS]]
    return "\n".join(top_chunks)


def build_prompt(question: str, history: list[str]) -> str:
    history_text = "\n".join(history[-6:]) or "Chưa có lịch sử hội thoại."
    context = search_context(question) or knowledge or "Không có dữ liệu tham khảo bổ sung."

    return f"""
Bạn là một trợ lý thân thiện, ấm áp và kiên nhẫn dành cho người lớn tuổi.

Nguyên tắc trả lời:
- Dùng tiếng Việt tự nhiên, đầy đủ dấu, dễ hiểu, câu ngắn gọn.
- Có thể mở đầu bằng các cụm nhẹ nhàng như "Dạ", "À", "Vâng".
- Nếu câu hỏi chưa rõ, hỏi lại ngắn gọn.
- Không tự ý đưa ra thông tin y tế nguy hiểm như một chẩn đoán chính xác.
- Ưu tiên dùng thông tin trong phần tham khảo khi có liên quan.

Lịch sử hội thoại:
{history_text}

Thông tin tham khảo:
{context}

Người dùng:
{question}

Trả lời:
""".strip()


def remember_turn(history: list[str], user_text: str, reply: str) -> None:
    history.append(f"Người dùng: {user_text}")
    history.append(f"Trợ lý: {reply}")
    if len(history) > MAX_HISTORY_ITEMS:
        del history[:-MAX_HISTORY_ITEMS]


def get_history() -> list[str]:
    return chat_store[get_session_id()]


def build_unavailable_message() -> str:
    if genai is None:
        return (
            "Dạ, ứng dụng chưa cài thư viện google-generativeai nên tôi chưa thể kết nối Gemini. "
            "Bạn hãy cài dependencies rồi thử lại nhé."
        )

    if not API_KEY:
        return (
            "Dạ, hiện chưa có GEMINI_API_KEY trong môi trường nên tôi chưa thể trả lời bằng Gemini. "
            "Bạn chỉ cần thêm API key vào file .env hoặc biến môi trường là được."
        )

    return "Dạ, hiện tôi chưa sẵn sàng để phản hồi. Bạn thử lại giúp tôi nhé."


def generate_reply(question: str, history: list[str]) -> str:
    if model is None:
        reply = build_unavailable_message()
        remember_turn(history, question, reply)
        return reply

    prompt = build_prompt(question, history)
    response = model.generate_content(prompt)
    reply = (getattr(response, "text", "") or "").strip()

    if not reply:
        reply = "Dạ, tôi chưa tạo được câu trả lời phù hợp. Bạn thử hỏi lại một chút nhé."

    remember_turn(history, question, reply)
    return reply


@app.route("/")
def index():
    return render_template("index.html", model_name=MODEL_NAME)


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "model_ready": model is not None,
            "knowledge_loaded": bool(knowledge_chunks),
        }
    )


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(silent=True) or {}
    user_text = (payload.get("message") or "").strip()

    if not user_text:
        return jsonify({"error": "Thiếu nội dung tin nhắn."}), 400

    reply = generate_reply(user_text, get_history())
    return jsonify({"reply": reply})


@app.route("/chat_stream", methods=["POST"])
def chat_stream():
    payload = request.get_json(silent=True) or {}
    user_text = (payload.get("message") or "").strip()

    if not user_text:
        return jsonify({"error": "Thiếu nội dung tin nhắn."}), 400

    history = get_history()

    @stream_with_context
    def generate():
        if model is None:
            reply = build_unavailable_message()
            remember_turn(history, user_text, reply)
            yield reply
            return

        prompt = build_prompt(user_text, history)
        full_text = ""

        try:
            response = model.generate_content(prompt, stream=True)
            for chunk in response:
                chunk_text = getattr(chunk, "text", "")
                if not chunk_text:
                    continue
                full_text += chunk_text
                yield chunk_text
        except Exception:
            full_text = (
                "Dạ, trong lúc kết nối Gemini đã có lỗi xảy ra. "
                "Bạn thử lại sau ít phút hoặc kiểm tra API key giúp tôi nhé."
            )
            yield full_text

        if not full_text.strip():
            full_text = "Dạ, tôi tạm thời chưa tạo được nội dung phản hồi."

        remember_turn(history, user_text, full_text.strip())

    return Response(generate(), mimetype="text/plain; charset=utf-8")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
