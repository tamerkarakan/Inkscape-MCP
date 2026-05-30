export const meta = {
  name: 'inkscape-mcp-conformance-review',
  description: 'Review the Inkscape MCP code against review-rubric.md (47 checks): per-check verdicts with concrete evidence, then adversarially verify blocker/major failures against false positives, and report confirmed blockers. Run AFTER DeepSeek delivers code on a branch.',
  phases: [
    { title: 'Inceleme' },
    { title: 'Dogrula' },
  ],
}

// --- Parametreler (Workflow args ile gecilebilir; yoksa varsayilan) ---
const ROOT = (args && args.root) || 'C:\\Users\\tamer\\Codex_Projects\\Inkscape MCP'
const RUBRIC = ROOT + '\\review-rubric.md'
const ARCH = ROOT + '\\architecture-v1.md'
const REF = ROOT + '\\reference\\README.md'
const SRC = ROOT + '\\src'
const TESTS = ROOT + '\\tests'
const BRANCH = (args && args.branch) || 'feat/v1-prototype'
const BASE = (args && args.base) || 'fbb45f9'

const REVIEW_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['section', 'checks'],
  properties: {
    section: { type: 'string' },
    checks: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['ref', 'severity', 'verdict', 'evidence'],
        properties: {
          ref: { type: 'string', description: 'Rubric kontrol referansi, or. Madde 14 veya F8' },
          severity: { type: 'string', description: 'blocker / major / minor (rubricten ayni)' },
          verdict: { type: 'string', description: 'pass / fail / partial / uncertain / n-a' },
          evidence: { type: 'string', description: 'SOMUT kanit: pass ise hangi dosya:satir/fonksiyon karsiliyor; fail ise neyin eksik/yanlis oldugu; mumkunse grep bulgusu' },
        },
      },
    },
  },
}

const VERIFY_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['ref', 'upheld', 'reasoning'],
  properties: {
    ref: { type: 'string' },
    upheld: { type: 'boolean', description: 'true = fail bulgusu AYAKTA kaliyor; false = yanlis pozitif (kod aslinda kontrolu karsiliyor)' },
    reasoning: { type: 'string', description: 'Refute denemesi: kodun kontrolu karsiladigi yer (dosya:satir) bulundu mu? Bulunamadiysa veya emin degilsen upheld=true' },
  },
}

log('Inkscape MCP conformance review: branch=' + BRANCH + ' base=' + BASE)

const SECTIONS = [
  { key: 'A', title: 'Durum & Tutarlilik (lock / revision / dosya-otorite)' },
  { key: 'B', title: 'Motorlar & Adresleme (DOM yaratim vs Inkscape islem)' },
  { key: 'C', title: 'CLI Guvenlik & Escape-hatch' },
  { key: 'D', title: 'MCP Yuzeyi & Dogruluk' },
]

// pipeline: her bolum once incelenir, sonra o bolumun blocker/major fail'leri adversarial dogrulanir.
// Bolumler arasinda bariyer YOK; bir bolumun dogrulamasi koşarken digeri hala incelenebilir.
const reviewed = await pipeline(
  SECTIONS,
  // Stage 1 — Inceleme
  (sec) => agent(
`Sen titiz bir KOD UYGUNLUK GOZDEN GECIRICISISIN. Inkscape MCP kodunu sozlesmeye karsi denetliyorsun.

ADIMLAR:
1) ${RUBRIC} dosyasini Read ile oku; SADECE bu bolume odaklan: "${sec.key}. ${sec.title}". O bolumdeki HER kontrol maddesini ele al.
2) ${ARCH} (baglayici kontrat) ve ${REF} (yer-gercegi corpus) referans alinacak.
3) Kodu Glob/Grep/Read ile gercekten incele: ${SRC} ve ${TESTS} altindaki .py dosyalari (Glob: **/*.py) + koktek pyproject.toml. Kod yoksa/dizin bossa o bolumdeki kontroller 'fail' (not-implemented) olur.

Her kontrol icin verdict uret:
- pass: kod kontrolu net karsiliyor (kaniti dosya:satir ver).
- fail: karsilamiyor veya hic yok (neyin eksik oldugunu yaz).
- partial: kismen karsiliyor.
- uncertain: koddan kesin anlasilmiyor.
- n-a: bu kontrol bu kod icin uygulanamaz (gerekcele).
evidence SOMUT olmali; tahmin yurutme, KODA BAK ve grep/dosya:satir kaniti ver. severity'yi rubrictekiyle ayni gir. Cikti TURKCE, semaya gore.`,
    { label: 'review:' + sec.key, phase: 'Inceleme', schema: REVIEW_SCHEMA }
  ),
  // Stage 2 — Adversarial dogrulama (yalniz blocker/major fail & partial)
  (review, sec) => {
    const checks = (review && review.checks) || []
    const toVerify = checks.filter(c =>
      (c.verdict === 'fail' || c.verdict === 'partial') &&
      (c.severity === 'blocker' || c.severity === 'major')
    )
    return parallel(toVerify.map(c => () =>
      agent(
`Sen kotucul bir DOGRULAYICISIN. Asagidaki uygunluk-bulgusunu (fail/partial) CURUTMEYE calis: gozden geciren bir yeri kacirmis ve kod aslinda bu kontrolu karsiliyor olabilir mi?

Kodu (${SRC}, ${TESTS}) Grep/Read ile kontrol et:
- Kontrolun karsilandigini KANITLARSAN (dosya:satir) -> upheld=false (yanlis pozitif).
- Karsilanmadigini dogrularsan VEYA emin olamazsan -> upheld=true (bulgu ayakta; potansiyel blocker insan icin sakli kalsin).

KONTROL: ${c.ref}  [severity: ${c.severity}]
GOZDEN GECIRENIN KANITI: ${c.evidence}

Cikti TURKCE, semaya gore.`,
        { label: 'verify:' + sec.key + ':' + c.ref, phase: 'Dogrula', schema: VERIFY_SCHEMA }
      ).then(v => ({ ...c, upheld: v ? v.upheld : true, verify_reasoning: v ? v.reasoning : 'dogrulama atlandi (upheld varsayildi)' }))
    )).then(verifiedList => {
      const byRef = {}
      verifiedList.filter(Boolean).forEach(v => { byRef[v.ref] = v })
      const merged = checks.map(c => (byRef[c.ref] ? byRef[c.ref] : c))
      return { section: sec.key, title: sec.title, checks: merged }
    })
  }
)

// --- Ozet (deterministik; Date/random yok) ---
const allChecks = reviewed.filter(Boolean).flatMap(s => (s && s.checks) || [])
const isFail = c => (c.verdict === 'fail' || c.verdict === 'partial') && c.upheld !== false
const confirmedFails = allChecks.filter(isFail)
const blockers = confirmedFails.filter(c => c.severity === 'blocker')
const majors = confirmedFails.filter(c => c.severity === 'major')
const refuted = allChecks.filter(c => (c.verdict === 'fail' || c.verdict === 'partial') && c.upheld === false)

return {
  branch: BRANCH,
  base: BASE,
  summary: {
    total_checks: allChecks.length,
    passed: allChecks.filter(c => c.verdict === 'pass').length,
    uncertain: allChecks.filter(c => c.verdict === 'uncertain').length,
    confirmed_fails: confirmedFails.length,
    refuted_false_positives: refuted.length,
    blockers: blockers.length,
    majors: majors.length,
    merge_ok: blockers.length === 0,
    blocker_refs: blockers.map(c => c.ref),
    major_refs: majors.map(c => c.ref),
  },
  sections: reviewed,
}
