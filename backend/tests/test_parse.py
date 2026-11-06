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

    abstract, body, no_coords, table = paras
    assert abstract["section"] == "Abstract" and abstract["page"] == 1
    assert body["section"] == "3.3 English Speech Recognition" and len(body["boxes"]) == 2
    assert no_coords["page"] == 6  # 沿用上一段页码
    assert table["kind"] == "table" and table["page"] == 7
    assert "LibriSpeech Clean | 2.7 | 2.7" in table["text"]
