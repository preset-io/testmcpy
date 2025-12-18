import React from 'react'

/**
 * Base skeleton element with shimmer animation
 */
const Skeleton = ({ className = '', width, height, circle = false }) => {
  const style = {}
  if (width) style.width = width
  if (height) style.height = height

  return (
    <div
      className={`bg-surface-elevated animate-pulse ${circle ? 'rounded-full' : 'rounded-lg'} ${className}`}
      style={style}
    />
  )
}

/**
 * Skeleton loader for tool cards in Explorer
 */
export const ToolCardSkeleton = () => {
  return (
    <div className="card-hover animate-pulse">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <Skeleton width="20px" height="20px" />
            <Skeleton width="200px" height="24px" />
          </div>
          <div className="mt-2 ml-8">
            <Skeleton width="100%" height="16px" />
            <Skeleton width="80%" height="16px" className="mt-1" />
          </div>
        </div>
        <Skeleton width="40px" height="40px" />
      </div>
    </div>
  )
}

/**
 * Skeleton loader for profile list items
 */
export const ProfileListSkeleton = () => {
  return (
    <div className="animate-pulse">
      <div className="flex items-center gap-2 px-2 py-1.5">
        <Skeleton width="14px" height="14px" />
        <div className="flex-1">
          <Skeleton width="150px" height="14px" />
          <Skeleton width="100px" height="12px" className="mt-1" />
        </div>
      </div>
    </div>
  )
}

/**
 * Skeleton loader for MCP server items
 */
export const MCPServerSkeleton = () => {
  return (
    <div className="ml-6 mt-1 animate-pulse">
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg">
        <div className="flex-1">
          <Skeleton width="120px" height="14px" />
          <Skeleton width="200px" height="12px" className="mt-1" />
        </div>
      </div>
    </div>
  )
}

/**
 * Skeleton loader for stats/counts
 */
export const StatSkeleton = () => {
  return (
    <div className="animate-pulse">
      <Skeleton width="60px" height="32px" />
      <Skeleton width="100px" height="14px" className="mt-2" />
    </div>
  )
}

/**
 * Skeleton loader for table rows
 */
export const TableRowSkeleton = ({ columns = 3 }) => {
  return (
    <tr className="animate-pulse">
      {Array.from({ length: columns }).map((_, idx) => (
        <td key={idx} className="px-4 py-3">
          <Skeleton height="16px" />
        </td>
      ))}
    </tr>
  )
}

/**
 * Skeleton loader for list items
 */
export const ListItemSkeleton = () => {
  return (
    <div className="flex items-center gap-3 py-2 animate-pulse">
      <Skeleton width="20px" height="20px" circle />
      <div className="flex-1">
        <Skeleton width="80%" height="16px" />
        <Skeleton width="60%" height="14px" className="mt-1" />
      </div>
    </div>
  )
}

/**
 * Full page skeleton for Explorer
 */
export const ExplorerPageSkeleton = () => {
  return (
    <div className="flex-1 overflow-auto p-4 bg-background-subtle">
      <div className="max-w-5xl mx-auto space-y-4">
        {Array.from({ length: 5 }).map((_, idx) => (
          <ToolCardSkeleton key={idx} />
        ))}
      </div>
    </div>
  )
}

/**
 * Profile selector loading skeleton
 */
export const ProfileSelectorSkeleton = () => {
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-surface-elevated border border-border rounded-lg animate-pulse">
      <Skeleton width="16px" height="16px" />
      <Skeleton width="150px" height="16px" />
      <Skeleton width="16px" height="16px" className="ml-auto" />
    </div>
  )
}

export { Skeleton }
export default Skeleton
