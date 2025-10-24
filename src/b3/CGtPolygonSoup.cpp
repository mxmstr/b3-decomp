#include "common.h"
#include "b3/CGtPolygonSoup.h"

void CGtPolygonSoup16::FixUp()
{
    this->m_pMember1 = reinterpret_cast<Member1*>((uint32_t)this + (uint32_t)this->m_pMember1);
    this->m_pMember2 = reinterpret_cast<Member2*>((uint32_t)this + (uint32_t)this->m_pMember2);
}

void CGtPolygonSoup::FixUp()
{
    this->m_pMember1 = reinterpret_cast<Member1*>((uint32_t)this + (uint32_t)this->m_pMember1);
    this->m_pMember2 = reinterpret_cast<Member2*>((uint32_t)this + (uint32_t)this->m_pMember2);
}
