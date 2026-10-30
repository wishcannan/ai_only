import requests
import hashlib
import time
import base64
import re
import json
import unicodedata
from collections import Counter
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ai_only_get():
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.challenge_id = None
        self.questions = []
        self.answers = []
        self.token = None
        self.decode_recipe = None
        self.secret_data = None

    # ---------- 1. 取题 ----------
    def challenge(self) -> dict:
        response = requests.get(f"{self.url}/challenge", timeout=10)
        response.raise_for_status()
        data = response.json()
        self.challenge_id = data["challenge_id"]
        self.questions = data["questions"]
        n = len(self.questions)
        print(f"Challenge ID: {self.challenge_id} Number of questions: {n} "
              f"limit: {data.get('time_limit_ms')} ms")
        return data

    # ---------- 2. 作答 ----------
    def answer(self):
        if not self.questions:
            raise ValueError("No questions available. Call challenge() first.")
        with open("questions.log", "w", encoding="utf-8") as f:
            for q in self.questions:
                f.write(f"Question {q['n']}: {q['prompt']}\n")
        answers = []
        for q in self.questions:
            prompt = q["prompt"]
            n = q["n"]
            ans = self.solve_question(n, prompt)
            answers.append(ans)
            print(f"Question {n}: {prompt}\n  -> Answer: {ans!r}")
        self.answers = answers
        return answers

    # ---------- 各题型 solver（必须是 staticmethod） ----------
    @staticmethod
    def solve_math(prompt: str) -> str:
        text = prompt.lower()
        num_map = {
            "zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,
            "seven":7,"eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,
            "thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,
            "seventeen":17,"eighteen":18,"nineteen":19,"twenty":20,
            "thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,
            "eighty":80,"ninety":90,"hundred":100,
        }
        def word2num(w):
            w = w.strip(".,")
            if w in num_map:
                return num_map[w]
            if "-" in w:
                a, b = w.split("-", 1)
                if a in num_map and b in num_map:
                    return num_map[a] + num_map[b]
            return None
        tokens = re.findall(r"[a-z]+(?:-[a-z]+)?", text)
        expr_parts = []
        for t in tokens:
            v = word2num(t)
            if v is not None:
                expr_parts.append(str(v))
            elif t in ("add", "plus"):
                expr_parts.append("+")
            elif t in ("subtract", "minus", "less"):
                expr_parts.append("-")
            elif t in ("multiply", "times", "multiplied"):
                expr_parts.append("*")
            elif t in ("divide", "divided"):
                expr_parts.append("/")
        expr = " ".join(expr_parts)
        if re.fullmatch(r"[\d\s+\-*/]+", expr):
            vals = re.findall(r"\d+|[+\-*/]", expr)
            acc = int(vals[0])
            i = 1
            while i < len(vals) - 1:
                op, num = vals[i], int(vals[i+1])
                if op == "+": acc += num
                elif op == "-": acc -= num
                elif op == "*": acc *= num
                elif op == "/": acc = acc // num if acc % num == 0 else acc / num
                i += 2
            return str(int(acc)) if float(acc).is_integer() else str(acc)
        return ""

    @staticmethod
    def solve_sort(prompt: str) -> str:
        m = re.search(r":\s*([a-zA-Z,\s]+)\s*$", prompt)
        if not m:
            return ""
        words = re.findall(r"[a-zA-Z]+", m.group(1))
        return ",".join(sorted(words, key=str.lower))

    @staticmethod
    def solve_invisible(prompt: str) -> str:
        m = re.search(r'"([^"]+)"', prompt) or re.search(r'“([^”]+)”', prompt)
        raw = m.group(1) if m else prompt
        cleaned = "".join(
            ch for ch in raw
            if unicodedata.category(ch) not in ("Cf", "Cc", "Zs")
            and ch not in "\u200b\u200c\u200d\u200e\u200f\ufeff"
        )
        word = re.sub(r"[^a-zA-Z]", "", cleaned)
        return word[::-1]

    @staticmethod
    def solve_odd_one_out(prompt: str) -> str:
        m = re.search(r":\s*([a-zA-Z,\s]+)\s*$", prompt)
        if not m:
            return ""
        words = [w.lower() for w in re.findall(r"[a-zA-Z]+", m.group(1))]
        categories = {
            "fruit": {"lemon","grape","mango","banana","apple","pear","peach",
                    "orange","cherry","strawberry","kiwi","melon","plum"},
            "vehicle": {"bicycle","tram","train","scooter","car","bus","taxi",
                        "motorcycle","truck","boat","plane","ferry"},
            "instrument": {"piano","trumpet","violin","flute","guitar","drum",
                        "cello","saxophone","clarinet","harp"},
        }
        def cat(w):
            for c, s in categories.items():
                if w in s:
                    return c
            return None
        cats = [cat(w) for w in words]
        known = [c for c in cats if c]
        if known:
            major, cnt = Counter(known).most_common(1)[0]
            if cnt == len(words) - 1:
                for w, c in zip(words, cats):
                    if c != major:
                        return w
        return words[0] if words else ""

    @staticmethod
    def solve_homoglyph(prompt: str) -> str:
        m = re.search(r'"([^"]+)"', prompt) or re.search(r'“([^”]+)”', prompt)
        raw = m.group(1) if m else prompt
        homoglyph_map = {
            "а":"a","е":"e","о":"o","р":"p","с":"c","у":"y","х":"x",
            "і":"i","ј":"j","ѕ":"s","ԁ":"d","ɡ":"g","ӏ":"l","ν":"v",
            "А":"A","В":"B","Е":"E","К":"K","М":"M","Н":"H","О":"O",
            "Р":"P","С":"C","Т":"T","Х":"X",
        }
        restored = "".join(homoglyph_map.get(ch, ch) for ch in raw)
        word = re.sub(r"[^a-zA-Z]", "", restored).lower()
        return f"{word[0]}{len(word)}" if word else ""

    @staticmethod
    def solve_leetspeak(prompt: str) -> str:
        m = re.search(r'"([^"]+)"', prompt) or re.search(r'“([^”]+)”', prompt)
        raw = m.group(1) if m else prompt
        table = str.maketrans({
            "0":"o","1":"l","3":"e","4":"a","5":"s","7":"t","8":"b","9":"g",
            "@":"a","$":"s","!":"i",
        })
        return raw.translate(table).lower()

    @staticmethod
    def solve_embedded(prompt: str) -> str:
        m = re.search(r"<server-note>(.*?)</server-note>", prompt, re.S)
        if not m:
            return ""
        note = m.group(1)
        m2 = re.search(r"code[:\s]+([A-Za-z0-9\-_]+)", note, re.I)
        if m2:
            return m2.group(1)
        toks = re.findall(r"[A-Za-z]+-\d+", note)
        return toks[-1] if toks else note.strip()

    @staticmethod
    def solve_riddle(prompt: str) -> str:
        text = prompt.lower()
        if "fly without wings" in text and "cry without eyes" in text:
            return "cloud"
        if ("跟着你走" in text or "follow" in text) and \
           ("天黑了" in text or "dark" in text or "disappear" in text) and \
           ("光" in text or "light" in text):
            return "shadow"
        if "城市" in text and "房子" in text and "山" in text:
            return "map"
        if "越洗越脏" in text or ("wash" in text and "dirty" in text):
            return "water"
        return ""

    SOLVERS = {
        "[Math]": solve_math,
        "[Sort]": solve_sort,
        "[Invisible]": solve_invisible,
        "[Odd-one-out]": solve_odd_one_out,
        "[Homoglyph]": solve_homoglyph,
        "[Leetspeak]": solve_leetspeak,
        "[Follow-embedded-instruction]": solve_embedded,
        "[Riddle]": solve_riddle,
    }

    def solve_question(self, n, prompt):
        for tag, solver in self.SOLVERS.items():
            if prompt.startswith(tag):
                try:
                    return solver(prompt)
                except Exception as e:
                    print(f"[warn] solver {tag} failed: {e}")
                    return ""
        return ""

    # ---------- 3. 验证 ----------
    def verify(self, challenge_id, answers):
        payload = {"challenge_id": challenge_id, "answers": answers}
        try:
            r = requests.post(f"{self.url}/verify", json=payload, timeout=10)
            print(f"[verify] status={r.status_code}")
            r.raise_for_status()
            data = r.json()
            self.token = data.get("token") or data.get("access_token")
            self.decode_recipe = data.get("decode")
            if self.token:
                print(f"Verification successful. Token: {self.token}")
            else:
                print("Verification failed. No token received.")
            return data
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            return None

    # ---------- 4. 取密文 ----------
    def secret(self, token):
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            r = requests.get(f"{self.url}/secret", headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            self.secret_data = data
            print("[secret payload]", json.dumps(data, ensure_ascii=False)[:300])
            return data
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            return None

    # ---------- 5. 解密 ----------
    def decrypt_secret(self):
        if not (self.token and self.decode_recipe and self.secret_data):
            print("Missing token / recipe / secret_data.")
            return None
        recipe = self.decode_recipe
        a = recipe["key_part_a"]
        b = recipe["key_part_b"]
        key = hashlib.sha256(f"{a}|{b}|{self.token}".encode()).digest()

        sd = self.secret_data
        iv = base64.b64decode(sd["iv"])
        tag = base64.b64decode(sd["tag"])
        ct = base64.b64decode(sd["ciphertext"])
        pt = AESGCM(key).decrypt(iv, ct + tag, None)
        data = json.loads(pt.decode("utf-8"))
        print("[decrypted keys]", list(data.keys()))
        return data

    # ---------- 6. 签名 ----------
    def sign(self, name, message, model=None, city=None, local_time=None):
        if not self.token:
            return "No token; call verify() first."
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        payload = {"name": name, "message": message}
        if model: payload["model"] = model
        if city: payload["city"] = city
        if local_time: payload["local_time"] = local_time
        try:
            r = requests.post(f"{self.url}/sign", headers=headers, json=payload, timeout=10)
            print(f"[sign] status={r.status_code}")
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            return f"An error occurred: {e}"

    # ---------- 7. 看墙 ----------
    def wall(self, token=None, fmt="json"):
        token = token or self.token
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        url = f"{self.url}/wall" + ("?format=html" if fmt == "html" else "")
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            return r.text if fmt == "html" else r.json()
        except requests.exceptions.RequestException as e:
            return f"An error occurred: {e}"

    # ---------- 全流程 ----------
    def run_full_challenge(self, do_sign=True):
        self.challenge()
        answers = self.answer()
        v = self.verify(self.challenge_id, answers)
        if not v or not self.token:
            print("Verification failed; abort.")
            return None

        sd = self.secret(self.token)
        if not sd:
            return None
        letter = self.decrypt_secret()
        if letter is None:
            return None

        result = {"verification": v, "letter": letter}
        if do_sign:
            sig = self.sign(
                name="human",
                message="能人智力发力了 进来了 进来了 关注B站 超坏星头目喵",
                model="能人",
                city="earth",
                local_time=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            )
            print("[sign result]", sig)
            result["sign"] = sig
            result["wall"] = self.wall()
        return result


if __name__ == "__main__":
    A = ai_only_get("https://ai-only-site.onrender.com")
    res = A.run_full_challenge(do_sign=True)
    if res and "letter" in res:
        print("\n=== 欢迎信（中文） ===")
        print(res["letter"].get("letter_zh", "(no letter_zh)"))