export default function EmptyState({ title, children, action }) {
  return (
    <section className="state-card empty-state">
      <span className="empty-state-mark" aria-hidden="true">
        +
      </span>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </section>
  )
}
