from app.pipeline.papers import parse_tei

TEI = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt><title level="a" type="main">Robust Speech Recognition via Large-Scale Weak Supervision</title></titleStmt>
      <publicationStmt><date type="published" when="2022-12-06">6 Dec 2022</date></publicationStmt>
      <sourceDesc><biblStruct><analytic>
        <author><persName><forename type="first">Alec</forename><surname>Radford</surname></persName></author>
        <author><persName><forename type="first">Jong</forename><forename type="middle">Wook</forename><surname>Kim</surname></persName></author>
        <idno type="arXiv">arXiv:2212.04356v1</idno>
      </analytic></biblStruct></sourceDesc>
    </fileDesc>
    <profileDesc><abstract><div><p coords="1,50,300,500,80">We study the capabilities of speech processing systems.</p></div></abstract></profileDesc>
  </teiHeader>
  <text>
    <body>
      <div><head n="3.3">English Speech Recognition</head>
        <p coords="6,50,100,250,40;6,50,140,250,40">Whisper models are evaluated zero-shot.</p>
        <p>No coordinates for this one.</p>
      </div>
      <div><head n="D.1">Models</head>
        <list><item coords="20,50,100,200,10">facebook/wav2vec2-large-960h</item><item>facebook/wav2vec2-base-100h</item></list>
      </div>
      <figure type="table" coords="7,54,80,240,160">
        <head>Table 2.</head>
        <figDesc>Detailed comparison of effective robustness.</figDesc>
        <table><row><cell>Dataset</cell><cell>wav2vec 2.0</cell><cell>Whisper</cell></row>
               <row><cell>LibriSpeech Clean</cell><cell>2.7</cell><cell>2.7</cell></row></table>
      </figure>
    </body>
  </text>
</TEI>"""


def test_parse_tei():
    header, paras = parse_tei(TEI)
    assert header["title"].startswith("Robust Speech")
    assert header["authors"] == ["Alec Radford", "Jong Wook Kim"]
    assert header["year"] == 2022 and header["arxiv_id"] == "2212.04356"

    abstract, body, no_coords, model_list, table = paras
    assert model_list["page"] == 20 and "wav2vec2-large-960h\nfacebook/wav2vec2-base-100h" in model_list["text"]
    assert abstract["section"] == "Abstract" and abstract["page"] == 1
    assert body["section"] == "3.3 English Speech Recognition" and len(body["boxes"]) == 2
    assert no_coords["page"] == 6  # 沿用上一段页码
    assert table["kind"] == "table" and table["page"] == 7
    assert "LibriSpeech Clean | 2.7 | 2.7" in table["text"]


def test_grobid_request_encodes_repeated_fields(monkeypatch):
    from app.config import settings
    from app.pipeline.papers import grobid_request

    monkeypatch.setattr(settings, "grobid_url", "http://grobid:8070")
    req = grobid_request(b"%PDF-1.4 test")
    body = req.read()
    assert str(req.url) == "http://grobid:8070/api/processFulltextDocument"
    assert body.count(b'name="teiCoordinates"') == 3
    for value in (b"\r\n\r\np\r\n", b"\r\n\r\nhead\r\n", b"\r\n\r\nfigure\r\n"):
        assert value in body
    assert b'filename="paper.pdf"' in body and b"%PDF-1.4 test" in body


def test_grobid_end_to_end_with_mock(monkeypatch):
    import httpx

    from app.config import settings
    from app.pipeline import papers

    monkeypatch.setattr(settings, "grobid_url", "http://grobid:8070")

    def handler(request):
        assert b'name="teiCoordinates"' in request.read()
        return httpx.Response(200, text=TEI)

    real_client = httpx.Client
    monkeypatch.setattr(papers.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    header, paras, parser, warning = papers.parse_pdf(b"%PDF-1.4 test")
    assert parser == "grobid" and header["arxiv_id"] == "2212.04356"
    assert any(p["kind"] == "table" and p["page"] == 7 for p in paras)
    assert warning is None


def test_grobid_failure_falls_back_to_pypdf(monkeypatch):
    from app.config import settings
    from app.pipeline import papers

    monkeypatch.setattr(settings, "grobid_url", "http://grobid:8070")
    monkeypatch.setattr(papers, "parse_with_grobid", lambda data: (_ for _ in ()).throw(TypeError("boom")))
    monkeypatch.setattr(papers, "parse_with_pypdf", lambda data: ({"title": "x"}, [{"id": "p1", "kind": "text", "section": "",
                                                                                    "text": "hello world", "page": 1, "boxes": []}]))
    header, paras, parser, warning = papers.parse_pdf(b"%PDF")
    assert parser == "pypdf" and paras and "GROBID" in warning["zh"] and "GROBID" in warning["en"]
