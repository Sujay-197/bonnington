from bonnington.brain.chunker import SentenceChunker


def test_chunker_streams_sentences():
    c = SentenceChunker()
    assert c.feed("Ah. Brit") == ["Ah."]
    assert c.feed("ney, Mr. Smith owes me 3.5 quid! Fine") == ["Britney, Mr. Smith owes me 3.5 quid!"]
    assert c.flush() == ["Fine"]


def test_question_ellipsis_and_newline():
    c = SentenceChunker()
    assert c.feed("Really? Well… fine\nNext") == ["Really?", "Well…", "fine"]
    assert c.flush() == ["Next"]


def test_eg_not_split():
    c = SentenceChunker()
    assert c.feed("Things, e.g. exams, matter. ") == ["Things, e.g. exams, matter."]


def test_flush_empty():
    assert SentenceChunker().flush() == []
