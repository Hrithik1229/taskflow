export default function ErrorState({ message, onRetry }) {
  return (
    <section className="state-card error-state" role="alert">
      <h2>Something went wrong</h2>
      <p>{message}</p>
      <button className="secondary-button" type="button" onClick={onRetry}>
        Try again
      </button>
    </section>
  )
}
