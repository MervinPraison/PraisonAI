import contract


def req(prev=True, nonce=None, stream=False, path="/v1/chat/completions"):
    return {"path": path, "stream": stream, "has_prev_nonce": prev, "reply_nonce": nonce}


def good():
    return {"requests": [req(None, "NONCE-0001"), req(True, "NONCE-0002"), req(True, "NONCE-0003")]}


def test_passes():
    assert contract.check(good(), "Edited: NONCE-0003 done.") == []


def test_four_requests_fail():
    s = good()
    s["requests"].append(req(True, "NONCE-0004"))
    problems = contract.check(s, "NONCE-0004")
    assert any("expected 3 chat requests, saw 4" in p for p in problems)


def test_broken_chain_fails():
    s = good()
    s["requests"][1]["has_prev_nonce"] = False
    assert any("request 2" in p for p in contract.check(s, "NONCE-0003"))


def test_streaming_mismatch_fails():
    s = good()
    s["requests"][2]["stream"] = True
    assert any("streaming" in p for p in contract.check(s, "NONCE-0003"))


def test_final_output_must_carry_last_nonce():
    assert any("final output" in p for p in contract.check(good(), "NONCE-0002"))


def test_non_chat_paths_ignored():
    s = good()
    s["requests"].insert(0, {"path": "/v1/models", "stream": False, "has_prev_nonce": None,
                             "reply_nonce": None})
    assert contract.check(s, "NONCE-0003") == []
