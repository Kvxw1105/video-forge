export type PackStatus = 'enabled' | 'enabled_with_degradation' | 'disabled' | 'blocked'
export type PackTrust = 'LOCAL' | 'UNVERIFIED' | 'TRUSTED_BUILTIN'

export interface ProviderDependency {
  id: string
  version: string
  required: boolean
}

export interface DirectorPackSummary {
  id: string
  version: string
  name: string
  description: string
  sourceTrust: PackTrust
  status: PackStatus
  degradations: string[]
  referenceCount: number
  providerDependencies: ProviderDependency[]
  manifestDigest: string
  archiveDigest: string
}

export interface DirectorPackReference {
  path: string
  role: string
}

export interface DirectorPackManifest {
  id: string
  version: string
  name: string
  description: string
  publisher: { id: string; name: string }
  style: { anchor: string; avoid: string[] }
  rhythm: { visualDensity: string; motionPreference: string }
  continuity: { scope: string; anchor: string }
  candidates: { count: number }
  approval: { defaultMode: 'auto' | 'review' }
  references: DirectorPackReference[]
  presets: DirectorPackReference[]
  templates: { id: string; provider: string; useFor: string[] }[]
  dependencies: { providers: ProviderDependency[]; skills: { id: string; version: string; role: string }[] }
  editable: string[]
  [key: string]: unknown
}

export interface DirectorPackDetail extends DirectorPackSummary {
  manifest: DirectorPackManifest
}

export interface ResolvedDirectorPolicy {
  schemaVersion: 1
  compilerVersion: string
  pack: { id: string; version: string; manifestDigest: string; archiveDigest: string; sourceTrust: PackTrust }
  providers: { id: string; version: string; trust: PackTrust; ready: boolean }[]
  effectiveRouting: Record<string, string[]>
  effectiveApproval: { mode: 'auto' | 'review'; forceReview: boolean }
  effectiveReferences: DirectorPackReference[]
  degradations: string[]
  status: 'enabled' | 'enabled_with_degradation' | 'blocked'
}

export interface ProductionProfileSummary {
  id: string
  name: string
  description: string
}

export type DirectorSource =
  | { kind: 'profile'; id: string }
  | { kind: 'director_pack'; id: string; version: string }
