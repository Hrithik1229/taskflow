function getInitials(name) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length > 1) {
    return `${parts[0][0]}${parts.at(-1)[0]}`.toUpperCase()
  }
  return (parts[0] || '?').slice(0, 2).toUpperCase()
}

export default function Avatar({ name, size = 'medium' }) {
  return (
    <span className={`avatar avatar--${size}`} aria-label={name}>
      {getInitials(name)}
    </span>
  )
}
