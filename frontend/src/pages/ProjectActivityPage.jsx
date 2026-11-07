import { useParams } from 'react-router-dom'
import ProjectActivity from '../features/activity/ProjectActivity'

export default function ProjectActivityPage() {
  const { projectId } = useParams()
  return <ProjectActivity projectId={projectId} />
}

