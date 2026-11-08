import { errorMessage } from './api.service';

describe('errorMessage', () => {
  it('reads FastAPI details', () => {
    expect(errorMessage({ status: 422, error: { detail: 'unknown strategy: x' } })).toBe('unknown strategy: x');
    expect(errorMessage({ status: 422, error: { detail: [{ msg: 'too short' }, { msg: 'bad' }] } })).toBe(
      'too short; bad',
    );
  });

  it('explains an unreachable API and unknown errors', () => {
    expect(errorMessage({ status: 0 })).toBe('The API is unreachable.');
    expect(errorMessage({ status: 500, error: 'x' })).toBe('Request failed (500).');
  });
});
