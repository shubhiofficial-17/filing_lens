export interface Segment {
  text: string;
  marker: number | null;
}

/** "Revenue was $5 [1]. Costs [2]." -> text and marker segments, for clickable citations. */
export function segments(answer: string): Segment[] {
  const out: Segment[] = [];
  const re = /\[(\d+)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(answer)) !== null) {
    if (m.index > last) {
      out.push({ text: answer.slice(last, m.index), marker: null });
    }
    out.push({ text: m[0], marker: Number(m[1]) });
    last = m.index + m[0].length;
  }
  if (last < answer.length) {
    out.push({ text: answer.slice(last), marker: null });
  }
  return out;
}
