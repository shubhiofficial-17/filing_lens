import { segments } from './answer-text';

describe('segments', () => {
  it('splits text and citation markers', () => {
    expect(segments('Revenue was $5.0 million [1]. Costs fell [12].')).toEqual([
      { text: 'Revenue was $5.0 million ', marker: null },
      { text: '[1]', marker: 1 },
      { text: '. Costs fell ', marker: null },
      { text: '[12]', marker: 12 },
      { text: '.', marker: null },
    ]);
  });

  it('keeps text without markers whole', () => {
    expect(segments('No sources.')).toEqual([{ text: 'No sources.', marker: null }]);
  });
});
