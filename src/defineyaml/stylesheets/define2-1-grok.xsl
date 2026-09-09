<?xml version="1.0" encoding="utf-8"?>
<!--
  The MIT License (MIT)

  Copyright (c) 2013-2018 Lex Jansen

  Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
  associated documentation files (the "Software"), to deal in the Software without restriction,
  including without limitation the rights to use, copy, modify, merge, publish, distribute,
  sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:
  The above copyright notice and this permission notice shall be included in all copies or
  substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
  NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
  NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
  DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT
  OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
-->
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:odm="http://www.cdisc.org/ns/odm/v1.3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:def="http://www.cdisc.org/ns/def/v2.1" xmlns:xlink="http://www.w3.org/1999/xlink"
  xmlns:arm="http://www.cdisc.org/ns/arm/v1.0" xml:lang="en"
  exclude-result-prefixes="def xlink odm xsi arm">
  <xsl:output method="html" indent="no" encoding="utf-8" version="5.0"
    doctype-system="about:legacy-compat"/>

  <!-- ********************************************************************************************************* -->
  <!-- Stylesheet Parameters - defaults for on-page settings panel                                               -->
  <!-- ********************************************************************************************************* -->
  <xsl:param name="nCodeListItemDisplay" select="5"/>
  <xsl:param name="displayMethodsTable" select="1"/>
  <xsl:param name="displayCommentsTable" select="0"/>
  <xsl:param name="displayPrefix" select="0"/>
  <xsl:param name="displayLengthDFormatSD" select="0"/>

  <!-- ********************************************************************************************************* -->
  <!-- File:        define2-1.xsl                                                                                -->
  <!-- Description: Define-XML 2.1 + ARM → single-file HTML5 with editable display settings                      -->
  <!-- Author:      Lex Jansen, CDISC Data Exchange Standards Team                                               -->
  <!-- Changes:                                                                                                  -->
  <!--   2026-09-08 - Modernized HTML5/CSS/JS; on-page editable display parameters                               -->
  <!--   2019-02-11 - Fixed window title in browser                                                                               -->
  <!--   2018-11-21 - Code cleanup                                                                               -->
  <!--   2018-10-24 - Added PublishingSet to Standard display in CodeLists (Draft Define-XML 2.1)                -->
  <!--   2018-08-09 - Fixed issue when there is no ItemGroupDef/@def:ArchiveLocationID                           -->
  <!--   2018-07-24 - Change Derivation to Method                                                                -->
  <!--              - Added tags for unresolved references                                                       -->
  <!--              - Always use Name attribute in Datasets table and header row (instead of SASDatasetName)     -->
  <!--              - Show pointer for cursor for VLM hyperlinks and buttons to show they are clickable objects  -->
  <!--              - Fix bug  to allow Supplemental variable keys to be mid key-order, not just at the end      -->
  <!--                Also fixed this for AP domains that have SQ supplemental variables.                        -->
  <!--              - Use Name rather than SASDatasetName for consistency.                                       -->
  <!--   2018-04-20 - Removed def:Standard/IsDefault (Draft Define-XML 2.1)                                      -->
  <!--              - Added CodeList/def:IsNonStandard (Draft Define-XML 2.1)                                    -->
  <!--   2018-03-01 - Made ARM table background consistent with other tables.                                    -->
  <!--              - Restored separation line in ARM summary listing.                                           -->
  <!--              - Added more vertical spacing between Expand All/Collapse All VLM buttons.                   -->
  <!--              - Fixed bug where only one FormalExpression element was supported per MethodDef element.     -->
  <!--              - Changed LE and GE comparators to use Unicode &#x2264 and &#x2265.                          -->
  <!--              - Made links from datasets in ARM consistent. Both will now go to the summary dataset table. -->
  <!--   2018-02-26 - Added version 2.1 comments.                                                                -->
  <!--              - Improved Expand All/Collapse All VLM buttons rounded corners.                              -->
  <!--   2018-02-16 - Added Class/SubClass (Draft Define-XML 2.1)                                                -->
  <!--   2018-02-13 - Improved Expand All/Collapse All VLM buttons.                                              -->
  <!--   2018-01-30 - Change Expand All/Collapse All VLM to buttons.                                             -->
  <!--   2018-01-25 - Give VLM rows the same background color as governing row.                                  -->
  <!--              - Some label updates.                                                                        -->
  <!--   2017-12-27 - Add Condition column only when there is VLM.                                               -->
  <!--              - Collapse/expand VLM rows.                                                                  -->
  <!--   2017-12-06 - Sort ItemRefs in VLM by OrderNumber.                                                       -->
  <!--   2017-11-20 - Further tweaking of VLM within dataset variable tables, including nested VLM for SuppQuals.-->
  <!--              - Fixed collapsed study metadata display when an  attribute is empty.                        -->
  <!--   2017-11-20 - Initial implementation of VLM within dataset variable tables (no nested VLM yet).          -->
  <!--   2017-10-23 - Support for CodeListItem/Description and EnumeratedItem/Description (Draft Define-XML 2.1) -->
  <!--              - Support for Associated Persons Supplemental Qualifiers.                                    -->
  <!--   2017-08-28 - Small fixes: ISO8601 -> ISO 8601, No data -> No Data, NonStandard -> Non Standard.         -->
  <!--   2017-08-02 - Removed display of OIDs from CodeList tables.                                              -->
  <!--   2017-08-01 - Fixed display for named destination with '#20' (blank).                                    -->
  <!--   2017-07-31 - Fixed link to XPT transport files (/ItemGroupDef/def:leaf) to open external.               -->
  <!--              - Removed link to related dataset from the bottom of the table.                              -->
  <!--              - Improved breaks in composite WhereClause display.                                          -->
  <!--              - Added non-breaking space to codelist item display in variable table, which improves break. -->
  <!--              - Fixed linking to items in WhereClause that do not belong to the current ItemGroup, which   -->
  <!--                will only work for items that are referenced in an ItemGroup and can uniquely be found.    -->
  <!--   2017-07-23 - Improved display for VLM for SuppQuals.                                                    -->
  <!--   2017-07-21 - Added support for multiple destinations in a def:PDFPageRef/PageRefs attribute.            -->
  <!--   2017-07-17 - Added display of:                                                                          -->
  <!--                  ItemGroupDef/def:HasNoData, ItemRef/def:HasNoData (Draft Define-XML 2.1)                 -->
  <!--              - Added display of ItemRef/@Role in variable tables and VLM tables, when defined.            -->
  <!--              - Completed display of document references.                                                  -->
  <!--   2017-07-07 - Display round brackets with multiple def:WhereClauseRefs.                                  -->
  <!--   2017-06-19 - Consistency between SDS and ADaM.                                                          -->
  <!--   2017-06-05 - Changed displayCommentsTable parameter default to 0.                                       -->
  <!--   2017-05-23 - Added display of key variables as defined in SUPPxx datasets.                              -->
  <!--   2017-05-19 - Added display of ODM/@Context.                                                             -->
  <!--              - Added display of CodeListItem/@Rank and odm:EnumeratedItem/@Rank.                          -->
  <!--              - Added display of keys when they are part of SuppQuals.                                     -->
  <!--              - Changed column label "Controlled Terms or Format" to "Controlled Terms or ISO Format"      -->
  <!--              - Changed Methods label to "Derivations" and ValueLists to "Value Level Metadata"            -->
  <!--   2017-03-28 - Removed Key column from variable metadata table.                                           -->
  <!--   2017-03-19 - SDTM/SEND/ADaM variable metadata tables now have the same columns and headers.             -->
  <!--   2017-03-15 - Added Added link to MethodDef/FormalExpression from dataset/VLM table.                     -->
  <!--              - Honoring leading blanks in methods.                                                        -->
  <!--              - Honoring leading blanks in CodeListItem Decodes in the CodeLists table.                    -->
  <!--              - Removed check for valid ItemGroupDef/@Purpose values.                                      -->
  <!--   2017-02-16 - Added External CodeList comments display.                                                  -->
  <!--              - The TableItemDefSDS template now displays DisplayFormat instead of Length when available.  -->
  <!--   2017-01-10 - Fixed duplicate CRF title display.                                                         -->
  <!--   2016-12-07 - Fixed display of Origin Description when there is more than one.                           -->
  <!--   2016-11-15 - Switched Location and Documentation in dataset display.                                    -->
  <!--   2016-10-31 - Changed Standard/StandardVersion display to StudyName.                                     -->
  <!--   2016-08-25 - Removed duplicate Standard/StandardVersion display in Define-XML 2.1.                      -->
  <!--              - Making dataset names clickable instead of labels for consistency.                          -->
  <!--              - Variable name no longer links to VLM, but a separate superscript "VLM" link.               -->
  <!--              - In Analysis Results Details table, add link to dataset an analysis variable is coming from.-->
  <!--   2016-08-08 - Added external documents icon.                                                             -->
  <!--   2016-08-01 - Fixed external documents display in a new window for documents in TOC.                     -->
  <!--   2016-07-14 - Added Supplemental Documents container.                                                    -->
  <!--              - Open external documents (pdf) in a new window.                                             -->
  <!--   2016-07-05 - Added Page display to linkSinglePageHyperlink template.                                    -->
  <!--   2016-06-21 - Improved ARM arm:Code display by wrapping really long lines.                               -->
  <!--   2016-06-09 - Added displayPrefix and displayLengthDFormatSD parameters.                                 -->
  <!--              - Honoring linebreaks in methods (also changed to indent="no").                              -->
  <!--              - Changed Standard/@Package to Standard/@PublishingSet (Draft Define-XML 2.1).               -->
  <!--   2016-03-10 - Updated ItemDef display of: Length [Significant Digits] : Display Format.                  -->
  <!--   2016-03-09 - Added Comment and DocumentRef display (Drfat Define-XML 2.1) for MetaDataVersion and       -->
  <!--                CodeList.                                                                                  -->
  <!--              - Added display of:                                                                          -->
  <!--                  ItemGroupDef/def:StandardOID, ItemGroupDef/def:IsNonStandard, CodeList/def:StandardOID   -->
  <!--              - Added display of def:Origin/@Source (Draft Define-XML 2.1).                                -->
  <!--              - Added Standard table (Draft Define-XML 2.1).                                               -->
  <!--              - Added def:PDFPageRef/@Title                                                                -->
  <!--              - Changed the Method display to honor linebreaks.                                            -->
  <!--   2016-03-02 - Added prefixes in 'Derivation / Comment' and 'Source / Derivation / Comment' columns.      -->
  <!--              - Added display of MethodDef/FormalExpression.                                               -->
  <!--              - Added display of CodeList/Description.                                                     -->
  <!--              - Added display of def:Origin/Description and def:DocumentRef.                               -->
  <!--              - Added display of ValueList/Description (Draft Define-XML 2.1).                             -->
  <!--              - Added display of ExternalCodeList/ExternalCodeList/@ref.                                   -->
  <!--   2016-02-11 - Improved Controlled Terms or Format display for CodeList Items and Enumerated Items.       -->
  <!--                The number of CodeList Items to display in the "Controlled Terms or Format" column is now  -->
  <!--                driven by the parameter nCodeListItemDisplay (default=5).                                  -->
  <!--                For external dictionaries the dictionary and version are displayed in the "Controlled      -->
  <!--                Terms or Format" column below the link.                                                    -->
  <!--   2016-02-08 - CRF Origin display no longer hardcoded as "CRF Page", but uses the real title.             -->
  <!--              - Display of "ISO 8601" in the "Controlled Terms or Format" column is now completely driven  -->
  <!--                by the DataType.                                                                           -->
  <!--   2016-02-04 - Fixed issue with PDF pages that are invalid, for example 12A.                              -->
  <!--   2015-02-13 - Fixed issue where multiple documents would result in displaying the first document         -->
  <!--                multiple times in the Dataset and Value Level Metadata sections.                           -->
  <!--              - For displaying the annotated CRF documents:                                                -->
  <!--                When there is no def:AnnotatedCRF element, loop over the def:leaf elements and see if      -->
  <!--                these are referenced from any ItemDef/def:Origin/def:DocumentRef elements.                 -->
  <!--              - Added support for multiple def:Origin elements and multiple documents within a def:Origin. -->
  <!--              - Links to Annotated CRFs in def:Origin is no longer taken from the def:AnnotatedCRF element -->
  <!--   2015-01-16 - Added Study metadata display                                                               -->
  <!--              - Improved Analysis Parameter(s) display                                                     -->
  <!--   2014-08-29 - Added displayMethodsTable parameter.                                                       -->
  <!--              - Added link when href has a value in ExternalCodeList (AppendixExternalCodeLists template). -->
  <!--              - Many improvements for linking to external PDF documents with physical page references or   -->
  <!--                named destinations.                                                                        -->
  <!--   2013-12-12 - Fixed with non-existing CodeList being linked.                                             -->
  <!--   2013-08-10 - Fixed issue in value level where clause display.                                           -->
  <!--              - Removed Comment sorting.                                                                   -->
  <!--              - Added Analysis Results Metadata.                                                           -->
  <!--   2013-04-24 - Fixed issue in displayISO8601 template when ItemDef/@Name has length=1.                    -->
  <!--   2013-03-04 - Initial version.                                                                           -->
  <!--                                                                                                           -->
  <!-- ********************************************************************************************************* -->

  <xsl:variable name="STYLESHEET_VERSION" select="'2026-09-08'"/>

  <xsl:variable name="LOWERCASE" select="'abcdefghijklmnopqrstuvwxyz'"/>
  <xsl:variable name="UPPERCASE" select="'ABCDEFGHIJKLMNOPQRSTUVWXYZ'"/>

  <xsl:variable name="REFTYPE_PHYSICALPAGE">PhysicalRef</xsl:variable>
  <xsl:variable name="REFTYPE_NAMEDDESTINATION">NamedDestination</xsl:variable>

  <xsl:variable name="Comparator_EQ"><text> = </text></xsl:variable>
  <xsl:variable name="Comparator_NE"><text> &#x2260; </text></xsl:variable>
  <xsl:variable name="Comparator_LT"><text> &lt; </text></xsl:variable>
  <xsl:variable name="Comparator_LE"><text> &#x2264; </text></xsl:variable>
  <xsl:variable name="Comparator_GT"><text> &gt; </text></xsl:variable>
  <xsl:variable name="Comparator_GE"><text> &#x2265; </text></xsl:variable>

  <xsl:variable name="PREFIX_COMMENT_TEXT"><span class="prefix"><xsl:text>[Comment] </xsl:text></span></xsl:variable>
  <xsl:variable name="PREFIX_METHOD_TEXT"><span class="prefix"><xsl:text>[Method] </xsl:text></span></xsl:variable>
  <xsl:variable name="PREFIX_ORIGIN_TEXT"><span class="prefix"><xsl:text>[Origin] </xsl:text></span></xsl:variable>

  <xsl:variable name="g_StudyName" select="/odm:ODM/odm:Study[1]/odm:GlobalVariables[1]/odm:StudyName"/>
  <xsl:variable name="g_StudyDescription" select="/odm:ODM/odm:Study[1]/odm:GlobalVariables[1]/odm:StudyDescription"/>
  <xsl:variable name="g_ProtocolName" select="/odm:ODM/odm:Study[1]/odm:GlobalVariables[1]/odm:ProtocolName"/>

  <xsl:variable name="g_MetaDataVersion" select="/odm:ODM/odm:Study[1]/odm:MetaDataVersion[1]"/>
  <xsl:variable name="g_MetaDataVersionName" select="$g_MetaDataVersion/@Name"/>
  <xsl:variable name="g_MetaDataVersionDescription" select="$g_MetaDataVersion/@Description"/>
  <xsl:variable name="g_DefineVersion" select="$g_MetaDataVersion/@def:DefineVersion"/>

  <xsl:variable name="g_seqStandard" select="$g_MetaDataVersion/def:Standards/def:Standard"/>
  <xsl:variable name="g_seqItemGroupDefs" select="$g_MetaDataVersion/odm:ItemGroupDef"/>
  <xsl:variable name="g_seqItemDefs" select="$g_MetaDataVersion/odm:ItemDef"/>
  <xsl:variable name="g_seqItemDefsValueListRef" select="$g_MetaDataVersion/odm:ItemDef/def:ValueListRef"/>
  <xsl:variable name="g_seqCodeLists" select="$g_MetaDataVersion/odm:CodeList"/>
  <xsl:variable name="g_seqValueListDefs" select="$g_MetaDataVersion/def:ValueListDef"/>
  <xsl:variable name="g_seqMethodDefs" select="$g_MetaDataVersion/odm:MethodDef"/>
  <xsl:variable name="g_seqCommentDefs" select="$g_MetaDataVersion/def:CommentDef"/>
  <xsl:variable name="g_seqWhereClauseDefs" select="$g_MetaDataVersion/def:WhereClauseDef"/>
  <xsl:variable name="g_seqleafs" select="$g_MetaDataVersion/def:leaf"/>

  <xsl:variable name="g_StandardName">
    <xsl:choose>
      <xsl:when test="$g_MetaDataVersion/@def:StandardName">
        <xsl:value-of select="$g_MetaDataVersion/@def:StandardName"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$g_MetaDataVersion/def:Standards/def:Standard[1][@Type='IG']/@Name"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>
  <xsl:variable name="g_StandardVersion">
    <xsl:choose>
      <xsl:when test="$g_MetaDataVersion/@def:StandardVersion">
        <xsl:value-of select="$g_MetaDataVersion/@def:StandardVersion"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$g_MetaDataVersion/def:Standards/def:Standard[1][@Type='IG']/@Version"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- ***************************************************************** -->
  <!-- Create the HTML Header                                            -->
  <!-- ***************************************************************** -->
  <xsl:template match="/">
    <html lang="en">
      <xsl:call-template name="displaySystemProperties"/>
      <xsl:variable name="moreStandards">
        <xsl:if test="count($g_MetaDataVersion/def:Standards/def:Standard[@Type='IG']) > 1">
          <xsl:text>, ...</xsl:text>
        </xsl:if>
      </xsl:variable>
      <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <meta name="color-scheme" content="light dark"/>
        <title>
          <xsl:value-of select="$g_StudyName"/>: <xsl:value-of select="$g_StandardName"/>
          <xsl:text> </xsl:text>
          <xsl:value-of select="$g_StandardVersion"/>
          <xsl:value-of select="$moreStandards"/>
        </title>
        <xsl:call-template name="generateJavaScript"/>
        <xsl:call-template name="generateCSS"/>
      </head>
      <body>
        <xsl:attribute name="data-n-codelist"><xsl:value-of select="$nCodeListItemDisplay"/></xsl:attribute>
        <xsl:attribute name="data-methods"><xsl:value-of select="$displayMethodsTable"/></xsl:attribute>
        <xsl:attribute name="data-comments"><xsl:value-of select="$displayCommentsTable"/></xsl:attribute>
        <xsl:attribute name="data-prefix"><xsl:value-of select="$displayPrefix"/></xsl:attribute>
        <xsl:attribute name="data-length-sd"><xsl:value-of select="$displayLengthDFormatSD"/></xsl:attribute>

        <button type="button" id="menu-toggle" class="menu-toggle" aria-controls="menu" aria-expanded="false" title="Toggle navigation">
          <span class="menu-toggle-bars" aria-hidden="true"></span>
          <span class="visually-hidden">Menu</span>
        </button>
        <div id="sidebar-overlay" class="sidebar-overlay" hidden="hidden"></div>

        <xsl:call-template name="generateMenu"/>
        <xsl:call-template name="generateMain"/>
      </body>
    </html>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- Settings panel                                       -->
  <!-- **************************************************** -->
  <xsl:template name="displaySettingsPanel">
    <aside id="define-settings" class="settings-panel" aria-label="Display settings">
      <details open="open">
        <summary>Display settings</summary>
        <form id="settings-form" class="settings-form" onsubmit="return false;">
          <label class="settings-row">
            <span>Code list items shown</span>
            <input type="number" id="opt-nCodeListItemDisplay" min="0" max="999" step="1"
              value="{$nCodeListItemDisplay}"/>
          </label>
          <label class="settings-row">
            <input type="checkbox" id="opt-displayMethodsTable">
              <xsl:if test="string($displayMethodsTable) = '1'">
                <xsl:attribute name="checked">checked</xsl:attribute>
              </xsl:if>
            </input>
            <span>Show Methods table</span>
          </label>
          <label class="settings-row">
            <input type="checkbox" id="opt-displayCommentsTable">
              <xsl:if test="string($displayCommentsTable) = '1'">
                <xsl:attribute name="checked">checked</xsl:attribute>
              </xsl:if>
            </input>
            <span>Show Comments table</span>
          </label>
          <label class="settings-row">
            <input type="checkbox" id="opt-displayPrefix">
              <xsl:if test="string($displayPrefix) = '1'">
                <xsl:attribute name="checked">checked</xsl:attribute>
              </xsl:if>
            </input>
            <span>Show [Comment] / [Method] / [Origin] prefixes</span>
          </label>
          <label class="settings-row">
            <input type="checkbox" id="opt-displayLengthDFormatSD">
              <xsl:if test="string($displayLengthDFormatSD) = '1'">
                <xsl:attribute name="checked">checked</xsl:attribute>
              </xsl:if>
            </input>
            <span>Length [SignificantDigits] : Display Format</span>
          </label>
          <p class="settings-hint">Applies immediately on this page. Preferences are saved in this browser.</p>
        </form>
      </details>
    </aside>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- Bookmarks / Menu                                     -->
  <!-- **************************************************** -->
  <xsl:template name="generateMenu">
    <nav id="menu" role="navigation" aria-label="Document navigation">
      <a class="skip-link" href="#main">Skip to main content</a>
      <span class="study-name"><xsl:value-of select="$g_StudyName"/></span>

      <ul class="hmenu">
        <!-- Annotated CRF -->
        <xsl:choose>
          <xsl:when test="$g_MetaDataVersion/def:AnnotatedCRF">
            <xsl:for-each select="$g_MetaDataVersion/def:AnnotatedCRF/def:DocumentRef">
              <li class="hmenu-item">
                <span class="hmenu-bullet">+</span>
                <xsl:variable name="leafID" select="@leafID"/>
                <xsl:variable name="leaf" select="../../def:leaf[@ID=$leafID]"/>
                <xsl:choose>
                  <xsl:when test="../../def:leaf[@ID=$leafID]">
                    <a class="external tocItem">
                      <xsl:attribute name="href"><xsl:value-of select="$leaf/@xlink:href"/></xsl:attribute>
                      <xsl:value-of select="$leaf/def:title"/>
                    </a>
                  </xsl:when>
                  <xsl:otherwise>
                    <span class="tocItem unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$leafID"/><xsl:text>]</xsl:text></span>
                  </xsl:otherwise>
                </xsl:choose>
                <xsl:call-template name="displayImage"/>
              </li>
            </xsl:for-each>
          </xsl:when>
          <xsl:otherwise>
            <xsl:for-each select="$g_MetaDataVersion/def:leaf">
              <xsl:variable name="leafID" select="@ID"/>
              <xsl:if test="$g_seqItemDefs/def:Origin[@Type='CRF' or @Type='Collected']/def:DocumentRef[@leafID=$leafID]">
                <li class="hmenu-item">
                  <span class="hmenu-bullet">+</span>
                  <a class="external tocItem">
                    <xsl:attribute name="href"><xsl:value-of select="@xlink:href"/></xsl:attribute>
                    <xsl:value-of select="def:title"/>
                  </a>
                  <xsl:call-template name="displayImage"/>
                </li>
              </xsl:if>
            </xsl:for-each>
          </xsl:otherwise>
        </xsl:choose>

        <!-- Supplemental Documents -->
        <xsl:if test="$g_MetaDataVersion/def:SupplementalDoc">
          <li class="hmenu-submenu">
            <span onclick="toggle_submenu(this);" class="hmenu-bullet">+</span>
            <a class="tocItem" href="#main">Supplemental Documents</a>
            <ul>
              <xsl:for-each select="$g_MetaDataVersion/def:SupplementalDoc/def:DocumentRef">
                <xsl:variable name="leafIDs" select="@leafID"/>
                <xsl:variable name="leaf" select="../../def:leaf[@ID=$leafIDs]"/>
                <xsl:variable name="leafID" select="$leaf/@ID"/>
                <xsl:choose>
                  <xsl:when test="$g_MetaDataVersion/def:AnnotatedCRF/def:DocumentRef[@leafID=$leafID]"/>
                  <xsl:otherwise>
                    <li class="hmenu-item">
                      <xsl:choose>
                        <xsl:when test="../../def:leaf[@ID=$leafIDs]">
                          <span class="hmenu-bullet">+</span>
                          <a class="external tocItem">
                            <xsl:attribute name="href"><xsl:value-of select="$leaf/@xlink:href"/></xsl:attribute>
                            <xsl:value-of select="$leaf/def:title"/>
                          </a>
                        </xsl:when>
                        <xsl:otherwise>
                          <span class="hmenu-bullet">+</span>
                          <span class="tocItem unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$leafIDs"/><xsl:text>]</xsl:text></span>
                        </xsl:otherwise>
                      </xsl:choose>
                      <xsl:call-template name="displayImage"/>
                    </li>
                  </xsl:otherwise>
                </xsl:choose>
              </xsl:for-each>
            </ul>
          </li>
        </xsl:if>

        <!-- Standards -->
        <xsl:if test="/odm:ODM/odm:Study/odm:MetaDataVersion/def:Standards">
          <li class="hmenu-item">
            <span class="hmenu-bullet" onclick="toggle_submenu(this);">-</span>
            <a class="tocItem" href="#Standards_Table">Standards</a>
          </li>
        </xsl:if>

        <!-- Analysis Results Metadata -->
        <xsl:if test="/odm:ODM/odm:Study/odm:MetaDataVersion/arm:AnalysisResultDisplays">
          <li class="hmenu-submenu">
            <span class="hmenu-bullet" onclick="toggle_submenu(this);">+</span>
            <a class="tocItem" href="#ARM_Table_Summary">Analysis Results Metadata</a>
            <ul>
              <xsl:for-each select="/odm:ODM/odm:Study/odm:MetaDataVersion/arm:AnalysisResultDisplays/arm:ResultDisplay">
                <li class="hmenu-item">
                  <span class="hmenu-bullet">-</span>
                  <a class="tocItem">
                    <xsl:attribute name="href">#ARD.<xsl:value-of select="@OID"/></xsl:attribute>
                    <xsl:attribute name="title"><xsl:value-of select="./odm:Description/odm:TranslatedText"/></xsl:attribute>
                    <xsl:value-of select="@Name"/>
                  </a>
                </li>
              </xsl:for-each>
            </ul>
          </li>
        </xsl:if>

        <!-- Datasets -->
        <li class="hmenu-submenu">
          <span class="hmenu-bullet" onclick="toggle_submenu(this);">+</span>
          <a class="tocItem" href="#datasets">Datasets</a>
          <ul>
            <xsl:for-each select="$g_seqItemGroupDefs">
              <li class="hmenu-item">
                <span class="hmenu-bullet">-</span>
                <a class="tocItem">
                  <xsl:attribute name="href">#IG.<xsl:value-of select="@OID"/></xsl:attribute>
                  <xsl:value-of select="concat(@Name, ' (', ./odm:Description/odm:TranslatedText, ')')"/>
                </a>
              </li>
            </xsl:for-each>
          </ul>
        </li>

        <!-- Controlled Terminology -->
        <xsl:if test="$g_seqCodeLists">
          <li class="hmenu-submenu">
            <span onclick="toggle_submenu(this);" class="hmenu-bullet">+</span>
            <a href="#decodelist" class="tocItem">Controlled Terminology</a>
            <ul>
              <xsl:if test="$g_seqCodeLists[odm:CodeListItem|odm:EnumeratedItem]">
                <li class="hmenu-submenu">
                  <span class="hmenu-bullet" onclick="toggle_submenu(this);">+</span>
                  <a class="tocItem" href="#decodelist">CodeLists</a>
                  <ul>
                    <xsl:for-each select="$g_seqCodeLists[odm:CodeListItem|odm:EnumeratedItem]">
                      <li class="hmenu-item">
                        <span class="hmenu-bullet">-</span>
                        <a class="tocItem">
                          <xsl:attribute name="href">#CL.<xsl:value-of select="@OID"/></xsl:attribute>
                          <xsl:value-of select="@Name"/>
                        </a>
                      </li>
                    </xsl:for-each>
                  </ul>
                </li>
              </xsl:if>
              <xsl:if test="$g_seqCodeLists[odm:ExternalCodeList]">
                <li class="hmenu-submenu">
                  <span class="hmenu-bullet" onclick="toggle_submenu(this);">+</span>
                  <a class="tocItem" href="#externaldictionary">External Dictionaries</a>
                  <ul>
                    <xsl:for-each select="$g_seqCodeLists[odm:ExternalCodeList]">
                      <li class="hmenu-item">
                        <span class="hmenu-bullet">-</span>
                        <a class="tocItem">
                          <xsl:attribute name="href">#CL.<xsl:value-of select="@OID"/></xsl:attribute>
                          <xsl:value-of select="@Name"/>
                        </a>
                      </li>
                    </xsl:for-each>
                  </ul>
                </li>
              </xsl:if>
            </ul>
          </li>
        </xsl:if>

        <!-- Methods (always in menu when present; visibility toggled on page) -->
        <xsl:if test="$g_seqMethodDefs">
          <li class="hmenu-submenu" data-section="methods">
            <span class="hmenu-bullet" onclick="toggle_submenu(this);">+</span>
            <a class="tocItem" href="#compmethod">Methods</a>
            <ul>
              <xsl:for-each select="$g_seqMethodDefs">
                <li class="hmenu-item">
                  <span class="hmenu-bullet">-</span>
                  <a class="tocItem">
                    <xsl:attribute name="href">#MT.<xsl:value-of select="@OID"/></xsl:attribute>
                    <xsl:value-of select="@Name"/>
                  </a>
                </li>
              </xsl:for-each>
            </ul>
          </li>
        </xsl:if>

        <!-- Comments (always in menu when present; visibility toggled on page) -->
        <xsl:if test="$g_seqCommentDefs">
          <li class="hmenu-submenu" data-section="comments">
            <span class="hmenu-bullet" onclick="toggle_submenu(this);">+</span>
            <a class="tocItem" href="#comment">Comments</a>
            <ul>
              <xsl:for-each select="$g_seqCommentDefs">
                <li class="hmenu-item">
                  <span class="hmenu-bullet">-</span>
                  <a class="tocItem">
                    <xsl:attribute name="href">#COMM.<xsl:value-of select="@OID"/></xsl:attribute>
                    <xsl:value-of select="@OID"/>
                  </a>
                </li>
              </xsl:for-each>
            </ul>
          </li>
        </xsl:if>
      </ul>

      <xsl:call-template name="displayButtons"/>
    </nav>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- Main content                                         -->
  <!-- **************************************************** -->
  <xsl:template name="generateMain">
    <main id="main" role="main">
      <div class="docinfo">
        <xsl:call-template name="displayODMCreationDateTimeDate"/>
        <xsl:call-template name="displayDefineXMLVersion"/>
        <xsl:call-template name="displayContext"/>
        <xsl:call-template name="displayStylesheetDate"/>
      </div>

      <xsl:call-template name="displaySettingsPanel"/>

      <xsl:call-template name="tableStudyMetadata">
        <xsl:with-param name="g_StandardName" select="$g_StandardName"/>
        <xsl:with-param name="g_StandardVersion" select="$g_StandardVersion"/>
        <xsl:with-param name="g_StudyName" select="$g_StudyName"/>
        <xsl:with-param name="g_StudyDescription" select="$g_StudyDescription"/>
        <xsl:with-param name="g_ProtocolName" select="$g_ProtocolName"/>
        <xsl:with-param name="g_MetaDataVersionName" select="$g_MetaDataVersionName"/>
        <xsl:with-param name="g_MetaDataVersionDescription" select="$g_MetaDataVersionDescription"/>
      </xsl:call-template>

      <xsl:if test="/odm:ODM/odm:Study/odm:MetaDataVersion/def:Standards">
        <xsl:call-template name="tableStandards"/>
      </xsl:if>

      <xsl:if test="/odm:ODM/odm:Study/odm:MetaDataVersion/arm:AnalysisResultDisplays">
        <xsl:call-template name="tableAnalysisResultsSummary"/>
        <xsl:call-template name="tableAnalysisResultsDetails"/>
      </xsl:if>

      <xsl:call-template name="tableItemGroups"/>

      <xsl:for-each select="$g_seqItemGroupDefs">
        <xsl:call-template name="tableItemDefs"/>
      </xsl:for-each>

      <xsl:call-template name="tableCodeLists"/>
      <xsl:call-template name="tableExternalCodeLists"/>

      <!-- Always generate when data exists; visibility controlled on page -->
      <xsl:if test="$g_seqMethodDefs">
        <xsl:call-template name="tableMethods"/>
      </xsl:if>
      <xsl:if test="$g_seqCommentDefs">
        <xsl:call-template name="tableComments"/>
      </xsl:if>
    </main>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- Study Metadata                                       -->
  <!-- **************************************************** -->
  <xsl:template name="tableStudyMetadata">
    <xsl:param name="g_StandardName"/>
    <xsl:param name="g_StandardVersion"/>
    <xsl:param name="g_StudyName"/>
    <xsl:param name="g_StudyDescription"/>
    <xsl:param name="g_ProtocolName"/>
    <xsl:param name="g_MetaDataVersionName"/>
    <xsl:param name="g_MetaDataVersionDescription"/>

    <div class="study-metadata">
      <dl class="study-metadata">
        <xsl:if test="$g_MetaDataVersion/@def:StandardName">
          <dt>Standard</dt>
          <dd>
            <xsl:value-of select="$g_StandardName"/>
            <xsl:text> </xsl:text>
            <xsl:value-of select="$g_StandardVersion"/>
          </dd>
        </xsl:if>
        <dt>Study Name</dt>
        <dd><xsl:value-of select="$g_StudyName"/></dd>
        <dt>Study Description</dt>
        <dd><xsl:value-of select="$g_StudyDescription"/></dd>
        <dt>Protocol Name</dt>
        <dd><xsl:value-of select="$g_ProtocolName"/></dd>
        <dt>Metadata Name</dt>
        <dd><xsl:value-of select="$g_MetaDataVersionName"/></dd>
        <xsl:if test="$g_MetaDataVersionDescription">
          <dt>Metadata Description</dt>
          <dd><xsl:value-of select="$g_MetaDataVersionDescription"/></dd>
        </xsl:if>
      </dl>
      <xsl:if test="$g_MetaDataVersion/@def:CommentOID">
        <div class="description">
          <xsl:call-template name="displayComment">
            <xsl:with-param name="CommentOID" select="$g_MetaDataVersion/@def:CommentOID"/>
            <xsl:with-param name="CommentPrefix" select="1"/>
            <xsl:with-param name="element" select="'p'"/>
          </xsl:call-template>
        </div>
      </xsl:if>
    </div>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- Standards                                            -->
  <!-- **************************************************** -->
  <xsl:template name="tableStandards">
    <h1 class="invisible">Standards for Study <xsl:value-of select="/odm:ODM/odm:Study/odm:GlobalVariables/odm:StudyName"/></h1>
    <div class="containerbox">
      <table id="Standards_Table" summary="Standards">
        <caption class="header">Standards for Study <xsl:value-of select="/odm:ODM/odm:Study/odm:GlobalVariables/odm:StudyName"/></caption>
        <tr class="header">
          <th scope="col">Standard</th>
          <th scope="col">Type</th>
          <th scope="col">Status</th>
          <th scope="col">Documentation</th>
        </tr>
        <xsl:for-each select="$g_seqStandard">
          <xsl:call-template name="tableRowStandards"/>
        </xsl:for-each>
      </table>
    </div>
    <xsl:call-template name="lineBreak"/>
  </xsl:template>

  <xsl:template name="tableRowStandards">
    <xsl:element name="tr">
      <xsl:call-template name="setRowClassOddeven">
        <xsl:with-param name="rowNum" select="position()"/>
      </xsl:call-template>
      <xsl:attribute name="id">STD.<xsl:value-of select="@OID"/></xsl:attribute>
      <td>
        <xsl:value-of select="@Name"/><xsl:text> </xsl:text>
        <xsl:if test="@PublishingSet">
          <xsl:value-of select="@PublishingSet"/><xsl:text> </xsl:text>
        </xsl:if>
        <xsl:value-of select="@Version"/>
      </td>
      <td><xsl:value-of select="@Type"/></td>
      <td><xsl:value-of select="@Status"/></td>
      <td>
        <xsl:call-template name="displayComment">
          <xsl:with-param name="CommentOID" select="@def:CommentOID"/>
          <xsl:with-param name="CommentPrefix" select="1"/>
        </xsl:call-template>
      </td>
    </xsl:element>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- ARM Summary                                          -->
  <!-- **************************************************** -->
  <xsl:template name="tableAnalysisResultsSummary">
    <div class="containerbox">
      <h1 id="ARM_Table_Summary">Analysis Results Metadata - Summary</h1>
      <div class="arm-summary">
        <xsl:for-each select="/odm:ODM/odm:Study/odm:MetaDataVersion/arm:AnalysisResultDisplays/arm:ResultDisplay">
          <xsl:variable name="DisplayOID" select="@OID"/>
          <xsl:variable name="DisplayName" select="@Name"/>
          <xsl:variable name="Display" select="/odm:ODM/odm:Study/odm:MetaDataVersion/arm:AnalysisResultDisplays/arm:ResultDisplay[@OID=$DisplayOID]"/>
          <div class="arm-summary-resultdisplay">
            <a>
              <xsl:attribute name="href">#ARD.<xsl:value-of select="$DisplayOID"/></xsl:attribute>
              <xsl:value-of select="$DisplayName"/>
            </a>
            <span class="arm-display-title">
              <xsl:value-of select="./odm:Description/odm:TranslatedText"/>
            </span>
            <xsl:for-each select="./arm:AnalysisResult">
              <xsl:variable name="AnalysisResultID" select="./@OID"/>
              <p class="arm-summary-result">
                <a>
                  <xsl:attribute name="href">#AR.<xsl:value-of select="$AnalysisResultID"/></xsl:attribute>
                  <xsl:value-of select="./odm:Description/odm:TranslatedText"/>
                </a>
              </p>
            </xsl:for-each>
          </div>
        </xsl:for-each>
      </div>
    </div>
    <xsl:call-template name="lineBreak"/>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- ARM Details                                          -->
  <!-- **************************************************** -->
  <xsl:template name="tableAnalysisResultsDetails">
    <h1>Analysis Results Metadata - Detail</h1>
    <xsl:for-each select="/odm:ODM/odm:Study/odm:MetaDataVersion/arm:AnalysisResultDisplays/arm:ResultDisplay">
      <div class="containerbox">
        <xsl:variable name="DisplayOID" select="@OID"/>
        <xsl:variable name="DisplayName" select="@Name"/>
        <xsl:variable name="Display" select="/odm:ODM/odm:Study/odm:MetaDataVersion/arm:AnalysisResultDisplays/arm:ResultDisplay[@OID=$DisplayOID]"/>
        <a><xsl:attribute name="id">ARD.<xsl:value-of select="$DisplayOID"/></xsl:attribute></a>
        <xsl:element name="table">
          <xsl:attribute name="class">analysisresults-detail</xsl:attribute>
          <xsl:attribute name="summary">Analysis Results Metadata - Detail</xsl:attribute>
          <caption><xsl:value-of select="$DisplayName"/></caption>
          <tr>
            <th scope="col" class="arm-resultlabel">Display</th>
            <th scope="col">
              <xsl:for-each select="def:DocumentRef">
                <xsl:call-template name="displayDocumentRef">
                  <xsl:with-param name="element" select="'span'"/>
                </xsl:call-template>
              </xsl:for-each>
              <xsl:text> </xsl:text>
              <span class="arm-displaytitle"><xsl:value-of select="$Display/odm:Description/odm:TranslatedText"/></span>
            </th>
          </tr>
          <xsl:for-each select="$Display/arm:AnalysisResult">
            <xsl:variable name="AnalysisResultOID" select="@OID"/>
            <xsl:variable name="AnalysisResult" select="$Display/arm:AnalysisResult[@OID=$AnalysisResultOID]"/>
            <tr class="arm-analysisresult">
              <td>Analysis Result</td>
              <td>
                <span class="arm-resulttitle">
                  <xsl:attribute name="id">AR.<xsl:value-of select="$AnalysisResultOID"/></xsl:attribute>
                  <xsl:value-of select="odm:Description/odm:TranslatedText"/>
                </span>
              </td>
            </tr>
            <xsl:variable name="ParameterOID" select="$AnalysisResult/@ParameterOID"/>
            <tr>
              <td class="arm-label">Analysis Parameter(s)</td>
              <td>
                <xsl:if test="$ParameterOID">
                  <xsl:if test="count($g_seqItemDefs[@OID=$ParameterOID]) = 0">
                    <span class="unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$ParameterOID"/><xsl:text>]</xsl:text></span>
                  </xsl:if>
                </xsl:if>
                <xsl:for-each select="$AnalysisResult/arm:AnalysisDatasets/arm:AnalysisDataset">
                  <xsl:variable name="WhereClauseOID" select="def:WhereClauseRef/@WhereClauseOID"/>
                  <xsl:variable name="WhereClauseDef" select="$g_seqWhereClauseDefs[@OID=$WhereClauseOID]"/>
                  <xsl:variable name="ItemGroupOID" select="@ItemGroupOID"/>
                  <xsl:for-each select="$WhereClauseDef/odm:RangeCheck[@def:ItemOID=$ParameterOID]">
                    <xsl:variable name="whereRefItemOID" select="./@def:ItemOID"/>
                    <xsl:variable name="whereRefItemName" select="$g_seqItemDefs[@OID=$whereRefItemOID]/@Name"/>
                    <xsl:variable name="whereOP" select="./@Comparator"/>
                    <xsl:variable name="whereRefItemCodeListOID" select="$g_seqItemDefs[@OID=$whereRefItemOID]/odm:CodeListRef/@CodeListOID"/>
                    <xsl:variable name="whereRefItemCodeList" select="$g_seqCodeLists[@OID=$whereRefItemCodeListOID]"/>
                    <xsl:call-template name="ItemGroupItemLink">
                      <xsl:with-param name="ItemGroupOID" select="$ItemGroupOID"/>
                      <xsl:with-param name="ItemOID" select="$whereRefItemOID"/>
                      <xsl:with-param name="ItemName" select="$whereRefItemName"/>
                    </xsl:call-template>
                    <xsl:choose>
                      <xsl:when test="$whereOP = 'IN' or $whereOP = 'NOTIN'">
                        <xsl:text> </xsl:text>
                        <xsl:variable name="Nvalues" select="count(./odm:CheckValue)"/>
                        <xsl:choose>
                          <xsl:when test="$whereOP='IN'"><xsl:text> IN </xsl:text></xsl:when>
                          <xsl:otherwise><xsl:text> NOT IN </xsl:text></xsl:otherwise>
                        </xsl:choose>
                        <xsl:text> (</xsl:text>
                        <xsl:for-each select="./odm:CheckValue">
                          <xsl:variable name="CheckValueINNOTIN" select="."/>
                          <p class="linebreakcell">
                            <xsl:call-template name="displayValue">
                              <xsl:with-param name="Value" select="$CheckValueINNOTIN"/>
                              <xsl:with-param name="DataType" select="$g_seqItemDefs[@OID=$whereRefItemOID]/@DataType"/>
                              <xsl:with-param name="decode" select="1"/>
                              <xsl:with-param name="CodeList" select="$whereRefItemCodeList"/>
                            </xsl:call-template>
                            <xsl:if test="position() != $Nvalues"><xsl:value-of select="', '"/></xsl:if>
                          </p>
                        </xsl:for-each>
                        <xsl:text> ) </xsl:text>
                      </xsl:when>
                      <xsl:when test="$whereOP = 'EQ'">
                        <xsl:variable name="CheckValueEQ" select="./odm:CheckValue"/>
                        <xsl:text> = </xsl:text>
                        <xsl:call-template name="displayValue">
                          <xsl:with-param name="Value" select="$CheckValueEQ"/>
                          <xsl:with-param name="DataType" select="$g_seqItemDefs[@OID=$whereRefItemOID]/@DataType"/>
                          <xsl:with-param name="decode" select="1"/>
                          <xsl:with-param name="CodeList" select="$whereRefItemCodeList"/>
                        </xsl:call-template>
                      </xsl:when>
                      <xsl:when test="$whereOP = 'NE'">
                        <xsl:variable name="CheckValueNE" select="./odm:CheckValue"/>
                        <xsl:text> &#x2260; </xsl:text>
                        <xsl:call-template name="displayValue">
                          <xsl:with-param name="Value" select="$CheckValueNE"/>
                          <xsl:with-param name="DataType" select="$g_seqItemDefs[@OID=$whereRefItemOID]/@DataType"/>
                          <xsl:with-param name="decode" select="1"/>
                          <xsl:with-param name="CodeList" select="$whereRefItemCodeList"/>
                        </xsl:call-template>
                      </xsl:when>
                      <xsl:otherwise>
                        <xsl:variable name="CheckValueOTH" select="./odm:CheckValue"/>
                        <xsl:text> </xsl:text>
                        <xsl:choose>
                          <xsl:when test="$whereOP='LT'"><xsl:text> &lt; </xsl:text></xsl:when>
                          <xsl:when test="$whereOP='LE'"><xsl:text> &lt;= </xsl:text></xsl:when>
                          <xsl:when test="$whereOP='GT'"><xsl:text> &gt; </xsl:text></xsl:when>
                          <xsl:when test="$whereOP='GE'"><xsl:text> &gt;= </xsl:text></xsl:when>
                          <xsl:otherwise><xsl:value-of select="$whereOP"/></xsl:otherwise>
                        </xsl:choose>
                        <xsl:call-template name="displayValue">
                          <xsl:with-param name="Value" select="$CheckValueOTH"/>
                          <xsl:with-param name="DataType" select="$g_seqItemDefs[@OID=$whereRefItemOID]/@DataType"/>
                          <xsl:with-param name="decode" select="1"/>
                          <xsl:with-param name="CodeList" select="$whereRefItemCodeList"/>
                        </xsl:call-template>
                      </xsl:otherwise>
                    </xsl:choose>
                    <br/>
                    <xsl:if test="position() != last()"><xsl:text> and </xsl:text></xsl:if>
                  </xsl:for-each>
                </xsl:for-each>
              </td>
            </tr>
            <tr>
              <td class="arm-label">Analysis Variable(s)</td>
              <td>
                <xsl:for-each select="arm:AnalysisDatasets/arm:AnalysisDataset">
                  <xsl:variable name="ItemGroupOID" select="@ItemGroupOID"/>
                  <xsl:for-each select="arm:AnalysisVariable">
                    <xsl:variable name="ItemOID" select="@ItemOID"/>
                    <xsl:variable name="ItemDef" select="/odm:ODM/odm:Study/odm:MetaDataVersion/odm:ItemDef[@OID=$ItemOID]"/>
                    <p class="arm-analysisvariable">
                      <xsl:choose>
                        <xsl:when test="/odm:ODM/odm:Study/odm:MetaDataVersion/odm:ItemGroupDef[@OID=$ItemGroupOID]">
                          <a>
                            <xsl:attribute name="href">#<xsl:value-of select="$ItemGroupOID"/></xsl:attribute>
                            <xsl:value-of select="/odm:ODM/odm:Study/odm:MetaDataVersion/odm:ItemGroupDef[@OID=$ItemGroupOID]/@Name"/>
                          </a>
                        </xsl:when>
                        <xsl:otherwise>
                          <span class="unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$ItemGroupOID"/><xsl:text>]</xsl:text></span>
                        </xsl:otherwise>
                      </xsl:choose>
                      <xsl:text>.</xsl:text>
                      <xsl:choose>
                        <xsl:when test="/odm:ODM/odm:Study/odm:MetaDataVersion/odm:ItemGroupDef[@OID=$ItemGroupOID] and /odm:ODM/odm:Study/odm:MetaDataVersion/odm:ItemDef[@OID=$ItemOID]">
                          <a>
                            <xsl:attribute name="href">#<xsl:value-of select="$ItemGroupOID"/>.<xsl:value-of select="$ItemOID"/></xsl:attribute>
                            <xsl:value-of select="$ItemDef/@Name"/>
                          </a>
                          <xsl:text> (</xsl:text>
                          <xsl:value-of select="$ItemDef/odm:Description/odm:TranslatedText"/>
                          <xsl:text>)</xsl:text>
                        </xsl:when>
                        <xsl:otherwise>
                          <span class="unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$ItemOID"/><xsl:text>]</xsl:text></span>
                        </xsl:otherwise>
                      </xsl:choose>
                    </p>
                  </xsl:for-each>
                </xsl:for-each>
              </td>
            </tr>
            <tr>
              <td class="arm-label">Analysis Reason</td>
              <td><xsl:value-of select="$AnalysisResult/@AnalysisReason"/></td>
            </tr>
            <tr>
              <td class="arm-label">Analysis Purpose</td>
              <td><xsl:value-of select="$AnalysisResult/@AnalysisPurpose"/></td>
            </tr>
            <tr>
              <td class="arm-label">Data References (incl. Selection Criteria)</td>
              <td>
                <xsl:for-each select="$AnalysisResult/arm:AnalysisDatasets/arm:AnalysisDataset">
                  <xsl:variable name="ItemGroupOID" select="@ItemGroupOID"/>
                  <xsl:variable name="ItemGroupDef" select="/odm:ODM/odm:Study/odm:MetaDataVersion/odm:ItemGroupDef[@OID=$ItemGroupOID]"/>
                  <div class="arm-data-reference">
                    <xsl:choose>
                      <xsl:when test="$ItemGroupDef/@OID">
                        <a>
                          <xsl:attribute name="href">#<xsl:value-of select="$ItemGroupDef/@OID"/></xsl:attribute>
                          <xsl:attribute name="title"><xsl:value-of select="$ItemGroupDef/odm:Description/odm:TranslatedText"/></xsl:attribute>
                          <xsl:value-of select="$ItemGroupDef/@Name"/>
                        </a>
                      </xsl:when>
                      <xsl:otherwise>
                        <span class="unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$ItemGroupOID"/><xsl:text>]</xsl:text></span>
                      </xsl:otherwise>
                    </xsl:choose>
                    <xsl:text>  [</xsl:text>
                    <xsl:call-template name="displayWhereClause">
                      <xsl:with-param name="ValueItemRef" select="$AnalysisResult/arm:AnalysisDatasets/arm:AnalysisDataset[@ItemGroupOID=$ItemGroupOID]"/>
                      <xsl:with-param name="ItemGroupLink" select="$ItemGroupOID"/>
                      <xsl:with-param name="decode" select="0"/>
                      <xsl:with-param name="break" select="0"/>
                    </xsl:call-template>
                    <xsl:text>]</xsl:text>
                  </div>
                </xsl:for-each>
                <xsl:for-each select="$AnalysisResult/arm:AnalysisDatasets">
                  <xsl:call-template name="displayComment">
                    <xsl:with-param name="CommentOID" select="@def:CommentOID"/>
                    <xsl:with-param name="CommentPrefix" select="1"/>
                  </xsl:call-template>
                </xsl:for-each>
              </td>
            </tr>
            <xsl:for-each select="$AnalysisResult/arm:Documentation">
              <tr>
                <td class="arm-label">Documentation</td>
                <td>
                  <span><xsl:value-of select="$AnalysisResult/arm:Documentation/odm:Description/odm:TranslatedText"/></span>
                  <xsl:for-each select="def:DocumentRef">
                    <xsl:call-template name="displayDocumentRef"/>
                  </xsl:for-each>
                </td>
              </tr>
            </xsl:for-each>
            <xsl:for-each select="$AnalysisResult/arm:ProgrammingCode">
              <tr>
                <td class="arm-label">Programming Statements</td>
                <td>
                  <xsl:if test="@Context">
                    <span class="arm-code-context">[<xsl:value-of select="@Context"/>]</span>
                  </xsl:if>
                  <xsl:if test="arm:Code">
                    <pre class="arm-code"><xsl:value-of select="arm:Code"/></pre>
                  </xsl:if>
                  <div class="arm-code-ref">
                    <xsl:for-each select="def:DocumentRef">
                      <xsl:call-template name="displayDocumentRef"/>
                    </xsl:for-each>
                  </div>
                </td>
              </tr>
            </xsl:for-each>
          </xsl:for-each>
        </xsl:element>
      </div>
      <xsl:call-template name="linkTop"/>
      <xsl:call-template name="lineBreak"/>
    </xsl:for-each>
    <xsl:call-template name="lineBreak"/>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- Datasets summary                                     -->
  <!-- **************************************************** -->
  <xsl:template name="tableItemGroups">
    <a id="datasets"/>
    <h1 class="invisible">Datasets</h1>
    <div class="containerbox">
      <table summary="Data Definition Tables">
        <caption class="header">Datasets</caption>
        <tr class="header">
          <th scope="col">Dataset</th>
          <th scope="col">Description</th>
          <th scope="col">Class
            <xsl:if test="$g_seqItemGroupDefs/def:Class/def:SubClass/@Name"> - SubClass</xsl:if>
          </th>
          <th scope="col">Structure</th>
          <th scope="col">Purpose</th>
          <th scope="col">Keys</th>
          <th scope="col">Documentation</th>
          <th scope="col">Location</th>
        </tr>
        <xsl:for-each select="$g_seqItemGroupDefs">
          <xsl:call-template name="tableRowItemGroupDefs"/>
        </xsl:for-each>
      </table>
    </div>
    <xsl:call-template name="linkTop"/>
    <xsl:call-template name="lineBreak"/>
  </xsl:template>

  <xsl:template name="tableRowItemGroupDefs">
    <xsl:element name="tr">
      <xsl:call-template name="setRowClassOddeven">
        <xsl:with-param name="rowNum" select="position()"/>
      </xsl:call-template>
      <xsl:attribute name="id"><xsl:value-of select="@OID"/></xsl:attribute>
      <td>
        <a>
          <xsl:attribute name="href">#IG.<xsl:value-of select="@OID"/></xsl:attribute>
          <xsl:value-of select="@Name"/>
        </a>
        <xsl:call-template name="displayStandard">
          <xsl:with-param name="element" select="'span'"/>
        </xsl:call-template>
        <xsl:call-template name="displayNonStandard">
          <xsl:with-param name="element" select="'span'"/>
        </xsl:call-template>
        <xsl:call-template name="displayNoData">
          <xsl:with-param name="element" select="'span'"/>
        </xsl:call-template>
      </td>
      <td>
        <xsl:value-of select="odm:Description/odm:TranslatedText"/>
        <xsl:variable name="ParentDescription">
          <xsl:call-template name="getParentDescription">
            <xsl:with-param name="OID" select="@OID"/>
          </xsl:call-template>
        </xsl:variable>
        <xsl:if test="string-length(normalize-space($ParentDescription)) &gt; 0">
          <xsl:text> (</xsl:text><xsl:value-of select="$ParentDescription"/><xsl:text>)</xsl:text>
        </xsl:if>
      </td>
      <td><xsl:call-template name="displayItemGroupClass"/></td>
      <td><xsl:value-of select="@def:Structure"/></td>
      <td><xsl:value-of select="@Purpose"/></td>
      <td><xsl:call-template name="displayItemGroupKeys"/></td>
      <td>
        <xsl:call-template name="displayComment">
          <xsl:with-param name="CommentOID" select="@def:CommentOID"/>
          <xsl:with-param name="CommentPrefix" select="1"/>
        </xsl:call-template>
      </td>
      <xsl:variable name="archiveLocationID" select="@def:ArchiveLocationID"/>
      <xsl:variable name="archiveTitle">
        <xsl:choose>
          <xsl:when test="def:leaf[@ID=$archiveLocationID]"><xsl:value-of select="def:leaf[@ID=$archiveLocationID]/def:title"/></xsl:when>
          <xsl:otherwise><xsl:text>[unresolved: </xsl:text><xsl:value-of select="@def:ArchiveLocationID"/><xsl:text>]</xsl:text></xsl:otherwise>
        </xsl:choose>
      </xsl:variable>
      <td>
        <xsl:if test="@def:ArchiveLocationID">
          <xsl:call-template name="displayHyperlink">
            <xsl:with-param name="href" select="def:leaf[@ID=$archiveLocationID]/@xlink:href"/>
            <xsl:with-param name="anchor" select="''"/>
            <xsl:with-param name="title" select="$archiveTitle"/>
          </xsl:call-template>
        </xsl:if>
      </td>
    </xsl:element>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- ItemDefs (dataset variable tables)                   -->
  <!-- **************************************************** -->
  <xsl:template name="tableItemDefs">
    <a id="IG.{@OID}"/>
    <div class="containerbox">
      <h1 class="invisible">
        <xsl:value-of select="concat(./odm:Description/odm:TranslatedText, ' (', @Name, ') ')"/>
      </h1>
      <xsl:element name="table">
        <xsl:attribute name="summary">ItemGroup IG.<xsl:value-of select="@OID"/></xsl:attribute>
        <caption>
          <span><xsl:call-template name="displayItemGroupDefHeader"/></span>
        </caption>
        <xsl:call-template name="linkSuppQual"/>
        <xsl:call-template name="linkSQAP"/>
        <xsl:call-template name="linkParentDomain"/>
        <xsl:call-template name="linkApParentDomain"/>

        <xsl:variable name="nItemsWithVLM"><xsl:value-of select="count(./odm:ItemRef[@ItemOID=$g_seqItemDefsValueListRef/../@OID])"/></xsl:variable>
        <xsl:variable name="isSuppQual">
          <xsl:choose>
            <xsl:when test="starts-with(@Name, 'SUPP') or starts-with(@Name, 'SQAP')">1</xsl:when>
            <xsl:otherwise>0</xsl:otherwise>
          </xsl:choose>
        </xsl:variable>
        <xsl:variable name="addRoleColumn">
          <xsl:choose>
            <xsl:when test="count(./odm:ItemRef/@Role) > 0 or $isSuppQual='1'">1</xsl:when>
            <xsl:otherwise>0</xsl:otherwise>
          </xsl:choose>
        </xsl:variable>
        <xsl:variable name="addConditionColumn">
          <xsl:choose>
            <xsl:when test="$nItemsWithVLM > 0 and $isSuppQual='0'">1</xsl:when>
            <xsl:otherwise>0</xsl:otherwise>
          </xsl:choose>
        </xsl:variable>

        <tr class="header">
          <th scope="col">Variable</th>
          <xsl:if test="$addConditionColumn='1'">
            <th scope="col">Where Condition</th>
          </xsl:if>
          <th scope="col">Label / Description</th>
          <th scope="col">Type</th>
          <xsl:if test="$addRoleColumn='1'">
            <th scope="col">Role</th>
          </xsl:if>
          <th scope="col" class="length length-header-simple">Length or Display Format</th>
          <th scope="col" class="length length-header-full">Length [SignificantDigits] : Display Format</th>
          <th scope="col" abbr="Format">Controlled Terms or ISO Format</th>
          <th scope="col">Origin / Source / Method / Comment</th>
        </tr>

        <xsl:for-each select="./odm:ItemRef">
          <xsl:sort data-type="number" order="ascending" select="@OrderNumber"/>
          <xsl:variable name="ItemRef" select="."/>
          <xsl:variable name="ItemDefOID" select="@ItemOID"/>
          <xsl:variable name="ItemGroupDefOID" select="../@OID"/>
          <xsl:variable name="ItemDef" select="../../odm:ItemDef[@OID=$ItemDefOID]"/>
          <xsl:variable name="VLMClass">
            <xsl:choose>
              <xsl:when test="position() mod 2 = 0"><xsl:text>tableroweven</xsl:text></xsl:when>
              <xsl:otherwise><xsl:text>tablerowodd</xsl:text></xsl:otherwise>
            </xsl:choose>
          </xsl:variable>

          <xsl:element name="tr">
            <xsl:call-template name="setRowClassOddeven">
              <xsl:with-param name="rowNum" select="position()"/>
            </xsl:call-template>
            <td>
              <xsl:choose>
                <xsl:when test="$ItemDef/def:ValueListRef/@ValueListOID">
                  <xsl:value-of select="$ItemDef/@Name"/>
                  <xsl:choose>
                    <xsl:when test="$g_seqValueListDefs[@OID = $ItemDef/def:ValueListRef/@ValueListOID]">
                      <xsl:element name="span">
                        <xsl:attribute name="class">valuelist-reference</xsl:attribute>
                        <xsl:attribute name="onclick">toggle_vlm(this);</xsl:attribute>
                        <a>
                          <xsl:attribute name="id"><xsl:value-of select="../@OID"/>.<xsl:value-of select="$ItemDef/@OID"/></xsl:attribute>
                          <xsl:text>VLM</xsl:text>
                        </a>
                      </xsl:element>
                    </xsl:when>
                    <xsl:otherwise>
                      <span class="valuelist-no-reference">
                        <span class="unresolved"><xsl:text>[unresolved: VLM]</xsl:text></span>
                      </span>
                    </xsl:otherwise>
                  </xsl:choose>
                </xsl:when>
                <xsl:otherwise>
                  <xsl:choose>
                    <xsl:when test="$ItemDef">
                      <a>
                        <xsl:attribute name="id"><xsl:value-of select="../@OID"/>.<xsl:value-of select="$ItemDef/@OID"/></xsl:attribute>
                      </a>
                      <xsl:value-of select="$ItemDef/@Name"/>
                    </xsl:when>
                    <xsl:otherwise>
                      <span class="unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$ItemDefOID"/><xsl:text>]</xsl:text></span>
                    </xsl:otherwise>
                  </xsl:choose>
                </xsl:otherwise>
              </xsl:choose>
              <xsl:call-template name="displayNonStandard">
                <xsl:with-param name="element" select="'span'"/>
              </xsl:call-template>
              <xsl:call-template name="displayNoData">
                <xsl:with-param name="element" select="'span'"/>
              </xsl:call-template>
            </td>
            <xsl:if test="$addConditionColumn='1'"><td></td></xsl:if>
            <td><xsl:value-of select="$ItemDef/odm:Description/odm:TranslatedText"/></td>
            <td class="datatype"><xsl:value-of select="$ItemDef/@DataType"/></td>
            <xsl:if test="$addRoleColumn='1'">
              <td class="role"><xsl:value-of select="@Role"/></td>
            </xsl:if>
            <td class="number length-cell">
              <span class="length-simple">
                <xsl:call-template name="displayItemDefLengthDFormat">
                  <xsl:with-param name="ItemDef" select="$ItemDef"/>
                </xsl:call-template>
              </span>
              <span class="length-full">
                <xsl:call-template name="displayItemDefLengthSignDigitsDisplayFormat">
                  <xsl:with-param name="ItemDef" select="$ItemDef"/>
                </xsl:call-template>
              </span>
            </td>
            <td>
              <xsl:call-template name="displayItemDefDecodeList">
                <xsl:with-param name="itemDef" select="$ItemDef"/>
              </xsl:call-template>
              <xsl:call-template name="displayItemDefISO8601">
                <xsl:with-param name="itemDef" select="$ItemDef"/>
              </xsl:call-template>
            </td>
            <td>
              <xsl:call-template name="displayItemDefOrigin">
                <xsl:with-param name="itemDef" select="$ItemDef"/>
                <xsl:with-param name="OriginPrefix" select="1"/>
              </xsl:call-template>
              <xsl:call-template name="displayItemDefMethod">
                <xsl:with-param name="MethodOID" select="$ItemRef/@MethodOID"/>
                <xsl:with-param name="MethodPrefix" select="1"/>
              </xsl:call-template>
              <xsl:call-template name="displayComment">
                <xsl:with-param name="CommentOID" select="$ItemDef/@def:CommentOID"/>
                <xsl:with-param name="CommentPrefix" select="1"/>
              </xsl:call-template>
            </td>
          </xsl:element>

          <xsl:if test="$ItemDef/def:ValueListRef/@ValueListOID">
            <xsl:call-template name="tableValueListsInTable">
              <xsl:with-param name="OID" select="$ItemDef/def:ValueListRef/@ValueListOID"/>
              <xsl:with-param name="ParentItemDefOID" select="concat($ItemGroupDefOID, '.', $ItemDefOID)"/>
              <xsl:with-param name="addRoleColumn" select="$addRoleColumn"/>
              <xsl:with-param name="isSuppQual" select="$isSuppQual"/>
              <xsl:with-param name="VLMClass" select="$VLMClass"/>
            </xsl:call-template>
          </xsl:if>
        </xsl:for-each>
      </xsl:element>
    </div>
    <xsl:call-template name="linkTop"/>
    <xsl:call-template name="lineBreak"/>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- VLM inline                                           -->
  <!-- **************************************************** -->
  <xsl:template name="tableValueListsInTable">
    <xsl:param name="OID"/>
    <xsl:param name="ParentItemDefOID"/>
    <xsl:param name="addRoleColumn"/>
    <xsl:param name="isSuppQual"/>
    <xsl:param name="VLMClass"/>
    <xsl:for-each select="$g_seqValueListDefs[@OID=$OID]">
      <xsl:for-each select="./odm:ItemRef">
        <xsl:sort data-type="number" order="ascending" select="@OrderNumber"/>
        <xsl:variable name="ItemRef" select="."/>
        <xsl:variable name="valueDefOID" select="@ItemOID"/>
        <xsl:variable name="valueDef" select="../../odm:ItemDef[@OID=$valueDefOID]"/>
        <xsl:variable name="vlOID" select="../@OID"/>
        <xsl:variable name="parentDef" select="../../odm:ItemDef/def:ValueListRef[@ValueListOID=$vlOID]"/>
        <xsl:variable name="parentOID" select="$parentDef/../@OID"/>
        <xsl:variable name="ValueItemGroupOID" select="$g_seqItemGroupDefs/odm:ItemRef[@ItemOID=$parentOID]/../@OID"/>
        <xsl:variable name="whereOID" select="./def:WhereClauseRef/@WhereClauseOID"/>
        <xsl:variable name="whereDef" select="$g_seqWhereClauseDefs[@OID=$whereOID]"/>

        <xsl:element name="tr">
          <xsl:attribute name="class">vlm <xsl:value-of select="$VLMClass"/><xsl:text> </xsl:text><xsl:value-of select="$ParentItemDefOID"/></xsl:attribute>
          <td>
            <xsl:if test="$isSuppQual='1'">
              <div class="qval-indent">
                <xsl:text>&#x27A4;  </xsl:text>
                <xsl:call-template name="displayWhereClause">
                  <xsl:with-param name="ValueItemRef" select="$ItemRef"/>
                  <xsl:with-param name="ItemGroupLink" select="$ValueItemGroupOID"/>
                  <xsl:with-param name="decode" select="0"/>
                  <xsl:with-param name="break" select="1"/>
                </xsl:call-template>
              </div>
            </xsl:if>
            <xsl:if test="$isSuppQual='2'">
              <div class="qval-indent2">
                <xsl:text>&#x27A4;  </xsl:text>
                <xsl:call-template name="displayWhereClause">
                  <xsl:with-param name="ValueItemRef" select="$ItemRef"/>
                  <xsl:with-param name="ItemGroupLink" select="$ValueItemGroupOID"/>
                  <xsl:with-param name="decode" select="1"/>
                  <xsl:with-param name="break" select="1"/>
                </xsl:call-template>
              </div>
            </xsl:if>
            <xsl:call-template name="displayNoData">
              <xsl:with-param name="element" select="'span'"/>
            </xsl:call-template>
          </td>
          <xsl:if test="$isSuppQual='0'">
            <td>
              <xsl:call-template name="displayWhereClause">
                <xsl:with-param name="ValueItemRef" select="$ItemRef"/>
                <xsl:with-param name="ItemGroupLink" select="$ValueItemGroupOID"/>
                <xsl:with-param name="decode" select="1"/>
                <xsl:with-param name="break" select="1"/>
              </xsl:call-template>
            </td>
          </xsl:if>
          <td>
            <xsl:if test="$valueDef/odm:Description/odm:TranslatedText">
              <xsl:value-of select="$valueDef/odm:Description/odm:TranslatedText"/>
            </xsl:if>
          </td>
          <td class="datatype"><xsl:value-of select="$valueDef/@DataType"/></td>
          <xsl:if test="count($ItemRef/@Role) > 0 or $addRoleColumn='1'">
            <td class="role"><xsl:value-of select="$ItemRef/@Role"/></td>
          </xsl:if>
          <td class="number length-cell">
            <span class="length-simple">
              <xsl:call-template name="displayItemDefLengthDFormat">
                <xsl:with-param name="ItemDef" select="$valueDef"/>
              </xsl:call-template>
            </span>
            <span class="length-full">
              <xsl:call-template name="displayItemDefLengthSignDigitsDisplayFormat">
                <xsl:with-param name="ItemDef" select="$valueDef"/>
              </xsl:call-template>
            </span>
          </td>
          <td>
            <xsl:call-template name="displayItemDefDecodeList">
              <xsl:with-param name="itemDef" select="$valueDef"/>
            </xsl:call-template>
            <xsl:call-template name="displayItemDefISO8601">
              <xsl:with-param name="itemDef" select="$valueDef"/>
            </xsl:call-template>
          </td>
          <td>
            <xsl:call-template name="displayItemDefOrigin">
              <xsl:with-param name="itemDef" select="$valueDef"/>
              <xsl:with-param name="OriginPrefix" select="1"/>
            </xsl:call-template>
            <xsl:call-template name="displayItemDefMethod">
              <xsl:with-param name="MethodOID" select="$ItemRef/@MethodOID"/>
              <xsl:with-param name="MethodPrefix" select="1"/>
            </xsl:call-template>
            <xsl:call-template name="displayComment">
              <xsl:with-param name="CommentOID" select="$valueDef/@def:CommentOID"/>
              <xsl:with-param name="CommentPrefix" select="1"/>
            </xsl:call-template>
            <xsl:call-template name="displayComment">
              <xsl:with-param name="CommentOID" select="$whereDef/@def:CommentOID"/>
              <xsl:with-param name="CommentPrefix" select="1"/>
            </xsl:call-template>
          </td>
        </xsl:element>
        <xsl:if test="$valueDef/def:ValueListRef/@ValueListOID and $isSuppQual = '1'">
          <xsl:call-template name="tableValueListsInTable">
            <xsl:with-param name="OID" select="$valueDef/def:ValueListRef/@ValueListOID"/>
            <xsl:with-param name="ParentItemDefOID" select="$ParentItemDefOID"/>
            <xsl:with-param name="addRoleColumn" select="$addRoleColumn"/>
            <xsl:with-param name="isSuppQual" select="'2'"/>
            <xsl:with-param name="VLMClass" select="$VLMClass"/>
          </xsl:call-template>
        </xsl:if>
      </xsl:for-each>
    </xsl:for-each>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- CodeLists                                            -->
  <!-- **************************************************** -->
  <xsl:template name="tableCodeLists">
    <xsl:if test="$g_seqCodeLists[odm:CodeListItem|odm:EnumeratedItem]">
      <a id="decodelist"/>
      <div class="containerbox">
        <h1 class="header">CodeLists</h1>
        <xsl:for-each select="$g_seqCodeLists[odm:CodeListItem|odm:EnumeratedItem]">
          <xsl:choose>
            <xsl:when test="./odm:CodeListItem">
              <xsl:call-template name="tableCodeListItems"/>
            </xsl:when>
            <xsl:when test="./odm:EnumeratedItem">
              <xsl:call-template name="tableEnumeratedItems"/>
            </xsl:when>
          </xsl:choose>
        </xsl:for-each>
        <xsl:call-template name="linkTop"/>
        <xsl:call-template name="lineBreak"/>
      </div>
    </xsl:if>
  </xsl:template>

  <xsl:template name="tableCodeListItems">
    <xsl:variable name="n_extended" select="count(odm:CodeListItem/@def:ExtendedValue)"/>
    <div class="codelist">
      <xsl:attribute name="id">CL.<xsl:value-of select="@OID"/></xsl:attribute>
      <div class="codelist-caption">
        <xsl:value-of select="@Name"/>
        <xsl:if test="./odm:Alias/@Context = 'nci:ExtCodeID'">
          <xsl:text> [</xsl:text>
          <span class="nci"><xsl:value-of select="./odm:Alias/@Name"/></span>
          <xsl:text>]</xsl:text>
        </xsl:if>
        <xsl:call-template name="displayStandard">
          <xsl:with-param name="element" select="'span'"/>
        </xsl:call-template>
        <xsl:call-template name="displayNonStandard">
          <xsl:with-param name="element" select="'span'"/>
        </xsl:call-template>
        <xsl:call-template name="displayDescription"/>
        <xsl:if test="@def:CommentOID">
          <div class="description">
            <xsl:call-template name="displayComment">
              <xsl:with-param name="CommentOID" select="@def:CommentOID"/>
              <xsl:with-param name="CommentPrefix" select="1"/>
              <xsl:with-param name="element" select="'div'"/>
            </xsl:call-template>
          </div>
        </xsl:if>
      </div>
      <xsl:element name="table">
        <xsl:attribute name="summary">Controlled Term - <xsl:value-of select="@Name"/></xsl:attribute>
        <tr class="header">
          <th scope="col" class="codedvalue">Permitted Value (Code)</th>
          <th scope="col">Display Value (Decode)</th>
          <xsl:if test="./odm:CodeListItem/odm:Description/odm:TranslatedText">
            <th scope="col">Description</th>
          </xsl:if>
          <xsl:if test="./odm:CodeListItem/@Rank">
            <th scope="col">Rank</th>
          </xsl:if>
        </tr>
        <xsl:for-each select="./odm:CodeListItem">
          <xsl:sort data-type="number" select="@OrderNumber" order="ascending"/>
          <xsl:sort data-type="number" select="@Rank" order="ascending"/>
          <xsl:element name="tr">
            <xsl:call-template name="setRowClassOddeven">
              <xsl:with-param name="rowNum" select="position()"/>
            </xsl:call-template>
            <td>
              <xsl:value-of select="@CodedValue"/>
              <xsl:if test="./odm:Alias/@Context = 'nci:ExtCodeID'">
                <xsl:text> [</xsl:text>
                <span class="nci"><xsl:value-of select="./odm:Alias/@Name"/></span>
                <xsl:text>]</xsl:text>
              </xsl:if>
              <xsl:if test="@def:ExtendedValue='Yes'">
                <xsl:text> [</xsl:text><span class="extended">*</span><xsl:text>]</xsl:text>
              </xsl:if>
            </td>
            <td class="codelist-item-decode">
              <xsl:value-of select="./odm:Decode/odm:TranslatedText"/>
            </td>
            <xsl:if test="../odm:CodeListItem/odm:Description/odm:TranslatedText">
              <td><xsl:call-template name="displayItemDescription"/></td>
            </xsl:if>
            <xsl:if test="../odm:CodeListItem/@Rank">
              <td><xsl:value-of select="@Rank"/></td>
            </xsl:if>
          </xsl:element>
        </xsl:for-each>
      </xsl:element>
      <xsl:if test="$n_extended &gt; 0">
        <p class="footnote"><span class="super">*</span> Extended Value</p>
      </xsl:if>
    </div>
  </xsl:template>

  <xsl:template name="tableEnumeratedItems">
    <xsl:variable name="n_extended" select="count(odm:EnumeratedItem/@def:ExtendedValue)"/>
    <div class="codelist">
      <xsl:attribute name="id">CL.<xsl:value-of select="@OID"/></xsl:attribute>
      <div class="codelist-caption">
        <xsl:value-of select="@Name"/>
        <xsl:if test="./odm:Alias/@Context = 'nci:ExtCodeID'">
          <xsl:text> [</xsl:text>
          <span class="nci"><xsl:value-of select="./odm:Alias/@Name"/></span>
          <xsl:text>]</xsl:text>
        </xsl:if>
        <xsl:call-template name="displayStandard">
          <xsl:with-param name="element" select="'span'"/>
        </xsl:call-template>
        <xsl:call-template name="displayNonStandard">
          <xsl:with-param name="element" select="'span'"/>
        </xsl:call-template>
        <xsl:call-template name="displayDescription"/>
        <xsl:if test="@def:CommentOID">
          <div class="description">
            <xsl:call-template name="displayComment">
              <xsl:with-param name="CommentOID" select="@def:CommentOID"/>
              <xsl:with-param name="CommentPrefix" select="1"/>
              <xsl:with-param name="element" select="'div'"/>
            </xsl:call-template>
          </div>
        </xsl:if>
      </div>
      <xsl:element name="table">
        <xsl:attribute name="summary">Code List - <xsl:value-of select="@Name"/></xsl:attribute>
        <tr class="header">
          <th scope="col">Permitted Value (Code)</th>
          <xsl:if test="./odm:EnumeratedItem/odm:Description/odm:TranslatedText">
            <th scope="col">Description</th>
          </xsl:if>
          <xsl:if test="./odm:EnumeratedItem/@Rank">
            <th scope="col">Rank</th>
          </xsl:if>
        </tr>
        <xsl:for-each select="./odm:EnumeratedItem">
          <xsl:sort data-type="number" select="@OrderNumber" order="ascending"/>
          <xsl:sort data-type="number" select="@Rank" order="ascending"/>
          <xsl:element name="tr">
            <xsl:call-template name="setRowClassOddeven">
              <xsl:with-param name="rowNum" select="position()"/>
            </xsl:call-template>
            <td>
              <xsl:value-of select="@CodedValue"/>
              <xsl:if test="./odm:Alias/@Context = 'nci:ExtCodeID'">
                <xsl:text> [</xsl:text>
                <span class="nci"><xsl:value-of select="./odm:Alias/@Name"/></span>
                <xsl:text>]</xsl:text>
              </xsl:if>
              <xsl:if test="@def:ExtendedValue='Yes'">
                <xsl:text> [</xsl:text><span class="extended">*</span><xsl:text>]</xsl:text>
              </xsl:if>
            </td>
            <xsl:if test="../odm:EnumeratedItem/odm:Description/odm:TranslatedText">
              <td><xsl:call-template name="displayItemDescription"/></td>
            </xsl:if>
            <xsl:if test="../odm:EnumeratedItem/@Rank">
              <td><xsl:value-of select="@Rank"/></td>
            </xsl:if>
          </xsl:element>
        </xsl:for-each>
      </xsl:element>
      <xsl:if test="$n_extended &gt; 0">
        <p class="footnote"><span class="super">*</span> Extended Value</p>
      </xsl:if>
    </div>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- External dictionaries                                -->
  <!-- **************************************************** -->
  <xsl:template name="tableExternalCodeLists">
    <xsl:if test="$g_seqCodeLists[odm:ExternalCodeList]">
      <a id="externaldictionary"/>
      <h1 class="invisible">External Dictionaries</h1>
      <div class="containerbox">
        <xsl:element name="table">
          <xsl:attribute name="summary">External Dictionaries (MedDra, WHODRUG, ...)</xsl:attribute>
          <caption class="header">External Dictionaries</caption>
          <tr class="header">
            <th scope="col">Reference Name</th>
            <th scope="col">External Dictionary</th>
            <th scope="col">Dictionary Version</th>
          </tr>
          <xsl:for-each select="$g_seqCodeLists/odm:ExternalCodeList">
            <xsl:element name="tr">
              <xsl:attribute name="id">CL.<xsl:value-of select="../@OID"/></xsl:attribute>
              <xsl:call-template name="setRowClassOddeven">
                <xsl:with-param name="rowNum" select="position()"/>
              </xsl:call-template>
              <td>
                <xsl:value-of select="../@Name"/>
                <xsl:if test="../odm:Description/odm:TranslatedText">
                  <div class="description"><xsl:value-of select="../odm:Description/odm:TranslatedText"/></div>
                </xsl:if>
                <xsl:if test="../@def:CommentOID">
                  <div class="description">
                    <xsl:call-template name="displayComment">
                      <xsl:with-param name="CommentOID" select="../@def:CommentOID"/>
                      <xsl:with-param name="CommentPrefix" select="1"/>
                      <xsl:with-param name="element" select="'div'"/>
                    </xsl:call-template>
                  </div>
                </xsl:if>
              </td>
              <td>
                <xsl:choose>
                  <xsl:when test="@href">
                    <xsl:call-template name="displayHyperlink">
                      <xsl:with-param name="href" select="@href"/>
                      <xsl:with-param name="anchor" select="''"/>
                      <xsl:with-param name="title" select="@Dictionary"/>
                    </xsl:call-template>
                  </xsl:when>
                  <xsl:otherwise><xsl:value-of select="@Dictionary"/></xsl:otherwise>
                </xsl:choose>
                <xsl:if test="@ref">
                  <xsl:text> (</xsl:text>
                  <xsl:call-template name="displayHyperlink">
                    <xsl:with-param name="href" select="@ref"/>
                    <xsl:with-param name="anchor" select="''"/>
                    <xsl:with-param name="title" select="@ref"/>
                  </xsl:call-template>
                  <xsl:text>)</xsl:text>
                </xsl:if>
              </td>
              <td><xsl:value-of select="@Version"/></td>
            </xsl:element>
          </xsl:for-each>
        </xsl:element>
      </div>
      <xsl:call-template name="linkTop"/>
      <xsl:call-template name="lineBreak"/>
    </xsl:if>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- Methods                                              -->
  <!-- **************************************************** -->
  <xsl:template name="tableMethods">
    <a id="compmethod"/>
    <div class="containerbox section-methods" id="section-methods" data-section="methods">
      <h1 class="invisible">Methods</h1>
      <xsl:element name="table">
        <xsl:attribute name="summary">Methods</xsl:attribute>
        <caption class="header">Methods</caption>
        <tr class="header">
          <th scope="col">Method</th>
          <th scope="col">Type</th>
          <th scope="col">Description</th>
        </tr>
        <xsl:for-each select="$g_seqMethodDefs">
          <xsl:element name="tr">
            <xsl:attribute name="id">MT.<xsl:value-of select="@OID"/></xsl:attribute>
            <xsl:call-template name="setRowClassOddeven">
              <xsl:with-param name="rowNum" select="position()"/>
            </xsl:call-template>
            <td><xsl:value-of select="@Name"/></td>
            <td><xsl:value-of select="@Type"/></td>
            <td>
              <div class="method-code"><xsl:value-of select="./odm:Description/odm:TranslatedText"/></div>
              <xsl:if test="string-length(./odm:FormalExpression) &gt; 0">
                <xsl:for-each select="odm:FormalExpression">
                  <div class="formalexpression">
                    <span class="label">Formal Expression</span>
                    <xsl:if test="string-length(@Context) &gt; 0">
                      <xsl:text> [</xsl:text><xsl:value-of select="@Context"/><xsl:text>]</xsl:text>
                    </xsl:if>
                    <xsl:text>:</xsl:text>
                    <span class="formalexpression-code"><xsl:value-of select="."/></span>
                  </div>
                </xsl:for-each>
              </xsl:if>
              <xsl:for-each select="./def:DocumentRef">
                <xsl:call-template name="displayDocumentRef"/>
              </xsl:for-each>
            </td>
          </xsl:element>
        </xsl:for-each>
      </xsl:element>
    </div>
    <xsl:call-template name="linkTop"/>
    <xsl:call-template name="lineBreak"/>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- Comments                                             -->
  <!-- **************************************************** -->
  <xsl:template name="tableComments">
    <a id="comment"/>
    <div class="containerbox section-comments" id="section-comments" data-section="comments">
      <h1 class="invisible">Comments</h1>
      <xsl:element name="table">
        <xsl:attribute name="summary">Comments</xsl:attribute>
        <caption class="header">Comments</caption>
        <tr class="header">
          <th scope="col">CommentOID</th>
          <th scope="col">Description</th>
        </tr>
        <xsl:for-each select="$g_seqCommentDefs">
          <xsl:element name="tr">
            <xsl:attribute name="id">COMM.<xsl:value-of select="@OID"/></xsl:attribute>
            <xsl:call-template name="setRowClassOddeven">
              <xsl:with-param name="rowNum" select="position()"/>
            </xsl:call-template>
            <td><xsl:value-of select="@OID"/></td>
            <td>
              <xsl:value-of select="normalize-space(.)"/>
              <xsl:for-each select="./def:DocumentRef">
                <xsl:call-template name="displayDocumentRef"/>
              </xsl:for-each>
            </td>
          </xsl:element>
        </xsl:for-each>
      </xsl:element>
    </div>
    <xsl:call-template name="linkTop"/>
    <xsl:call-template name="lineBreak"/>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- Document refs, hyperlinks, helpers                   -->
  <!-- **************************************************** -->
  <xsl:template name="displayDocumentRef">
    <xsl:param name="element" select="'p'"/>
    <xsl:variable name="leafID" select="@leafID"/>
    <xsl:variable name="leaf" select="$g_seqleafs[@ID = $leafID]"/>
    <xsl:variable name="href" select="$leaf/@xlink:href"/>
    <xsl:choose>
      <xsl:when test="def:PDFPageRef">
        <xsl:for-each select="def:PDFPageRef">
          <xsl:variable name="title">
            <xsl:choose>
              <xsl:when test="count($leaf) = 0">
                <span class="unresolved">[unresolved: <xsl:value-of select="$leafID"/>]</span>
              </xsl:when>
              <xsl:when test="@Title"><xsl:value-of select="@Title"/></xsl:when>
              <xsl:otherwise><xsl:value-of select="$leaf/def:title"/></xsl:otherwise>
            </xsl:choose>
          </xsl:variable>
          <xsl:variable name="PageRefType" select="normalize-space(@Type)"/>
          <xsl:variable name="PageRefs" select="normalize-space(@PageRefs)"/>
          <xsl:variable name="PageFirst" select="normalize-space(@FirstPage)"/>
          <xsl:variable name="PageLast" select="normalize-space(@LastPage)"/>
          <xsl:element name="{$element}">
            <xsl:attribute name="class">linebreakcell</xsl:attribute>
            <xsl:choose>
              <xsl:when test="$PageRefType = $REFTYPE_PHYSICALPAGE">
                <xsl:call-template name="linkPages2Hyperlinks">
                  <xsl:with-param name="href" select="$href"/>
                  <xsl:with-param name="pagenumbers">
                    <xsl:choose>
                      <xsl:when test="$PageRefs"><xsl:value-of select="normalize-space($PageRefs)"/></xsl:when>
                      <xsl:when test="$PageFirst"><xsl:value-of select="normalize-space(concat($PageFirst, '-', $PageLast))"/></xsl:when>
                    </xsl:choose>
                  </xsl:with-param>
                  <xsl:with-param name="title" select="$title"/>
                  <xsl:with-param name="ShowTitle" select="1"/>
                  <xsl:with-param name="Separator">
                    <xsl:choose>
                      <xsl:when test="$PageRefs"><xsl:value-of select="' '"/></xsl:when>
                      <xsl:when test="$PageFirst"><xsl:value-of select="'-'"/></xsl:when>
                    </xsl:choose>
                  </xsl:with-param>
                </xsl:call-template>
              </xsl:when>
              <xsl:when test="$PageRefType = $REFTYPE_NAMEDDESTINATION">
                <xsl:call-template name="linkNamedDestinations2Hyperlinks">
                  <xsl:with-param name="href" select="$href"/>
                  <xsl:with-param name="destinations" select="$PageRefs"/>
                  <xsl:with-param name="title" select="$title"/>
                  <xsl:with-param name="ShowTitle" select="1"/>
                  <xsl:with-param name="Separator" select="' '"/>
                </xsl:call-template>
              </xsl:when>
            </xsl:choose>
          </xsl:element>
        </xsl:for-each>
      </xsl:when>
      <xsl:otherwise>
        <xsl:variable name="title">
          <xsl:choose>
            <xsl:when test="count($leaf) = 0">
              <span class="unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$leafID"/><xsl:text>]</xsl:text></span>
            </xsl:when>
            <xsl:otherwise><xsl:value-of select="$leaf/def:title"/></xsl:otherwise>
          </xsl:choose>
        </xsl:variable>
        <xsl:element name="{$element}">
          <xsl:attribute name="class">linebreakcell</xsl:attribute>
          <xsl:call-template name="displayHyperlink">
            <xsl:with-param name="href" select="$href"/>
            <xsl:with-param name="anchor" select="''"/>
            <xsl:with-param name="title" select="$title"/>
          </xsl:call-template>
        </xsl:element>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template name="linkPages2Hyperlinks">
    <xsl:param name="href"/>
    <xsl:param name="pagenumbers"/>
    <xsl:param name="title"/>
    <xsl:param name="ShowTitle"/>
    <xsl:param name="Separator"/>
    <xsl:variable name="OriginString" select="$pagenumbers"/>
    <xsl:variable name="first">
      <xsl:choose>
        <xsl:when test="contains($OriginString,$Separator)"><xsl:value-of select="substring-before($OriginString,$Separator)"/></xsl:when>
        <xsl:otherwise><xsl:value-of select="$OriginString"/></xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:variable name="rest" select="substring-after($OriginString,$Separator)"/>
    <xsl:if test="$ShowTitle != '0'">
      <xsl:value-of select="$title"/><xsl:text> [</xsl:text>
    </xsl:if>
    <xsl:if test="string-length($first) > 0">
      <xsl:choose>
        <xsl:when test="number($first)">
          <xsl:call-template name="displayHyperlink">
            <xsl:with-param name="href" select="$href"/>
            <xsl:with-param name="anchor" select="concat('#page=', $first)"/>
            <xsl:with-param name="title" select="$first"/>
          </xsl:call-template>
        </xsl:when>
        <xsl:otherwise><xsl:value-of select="$first"/></xsl:otherwise>
      </xsl:choose>
    </xsl:if>
    <xsl:if test="string-length($rest) > 0">
      <xsl:choose>
        <xsl:when test="contains($rest,$Separator)">
          <xsl:call-template name="linkPages2Hyperlinks">
            <xsl:with-param name="href" select="$href"/>
            <xsl:with-param name="pagenumbers" select="$rest"/>
            <xsl:with-param name="title" select="$title"/>
            <xsl:with-param name="ShowTitle" select="0"/>
            <xsl:with-param name="Separator" select="' '"/>
          </xsl:call-template>
        </xsl:when>
        <xsl:otherwise>
          <xsl:text> </xsl:text><xsl:value-of select="$Separator"/><xsl:text> </xsl:text>
          <xsl:choose>
            <xsl:when test="number($rest)">
              <xsl:call-template name="displayHyperlink">
                <xsl:with-param name="href" select="$href"/>
                <xsl:with-param name="anchor" select="concat('#page=', $rest)"/>
                <xsl:with-param name="title" select="$rest"/>
              </xsl:call-template>
              <xsl:text>]</xsl:text>
            </xsl:when>
            <xsl:otherwise>
              <xsl:value-of select="$rest"/><xsl:text>]</xsl:text>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:if>
    <xsl:if test="string-length($rest) = 0"><xsl:text>]</xsl:text></xsl:if>
  </xsl:template>

  <xsl:template name="linkNamedDestinations2Hyperlinks">
    <xsl:param name="href"/>
    <xsl:param name="destinations"/>
    <xsl:param name="title"/>
    <xsl:param name="ShowTitle"/>
    <xsl:param name="Separator"/>
    <xsl:variable name="OriginString" select="$destinations"/>
    <xsl:variable name="first">
      <xsl:choose>
        <xsl:when test="contains($OriginString,$Separator)"><xsl:value-of select="substring-before($OriginString,$Separator)"/></xsl:when>
        <xsl:otherwise><xsl:value-of select="$OriginString"/></xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:variable name="rest" select="substring-after($OriginString,$Separator)"/>
    <xsl:if test="$ShowTitle != '0'">
      <xsl:value-of select="$title"/><xsl:text> [</xsl:text>
    </xsl:if>
    <xsl:if test="string-length($first) > 0">
      <xsl:call-template name="displayHyperlink">
        <xsl:with-param name="href" select="$href"/>
        <xsl:with-param name="anchor" select="concat('#', $first)"/>
        <xsl:with-param name="title">
          <xsl:call-template name="stringReplace">
            <xsl:with-param name="string" select="$first"/>
            <xsl:with-param name="from" select="'#20'"/>
            <xsl:with-param name="to" select="' '"/>
          </xsl:call-template>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:if>
    <xsl:if test="string-length($rest) > 0">
      <xsl:choose>
        <xsl:when test="contains($rest,$Separator)">
          <xsl:call-template name="linkNamedDestinations2Hyperlinks">
            <xsl:with-param name="href" select="$href"/>
            <xsl:with-param name="destinations" select="$rest"/>
            <xsl:with-param name="title" select="$title"/>
            <xsl:with-param name="ShowTitle" select="0"/>
            <xsl:with-param name="Separator" select="' '"/>
          </xsl:call-template>
        </xsl:when>
        <xsl:otherwise>
          <xsl:text> </xsl:text><xsl:value-of select="$Separator"/><xsl:text> </xsl:text>
          <xsl:call-template name="displayHyperlink">
            <xsl:with-param name="href" select="$href"/>
            <xsl:with-param name="anchor" select="concat('#', $rest)"/>
            <xsl:with-param name="title">
              <xsl:call-template name="stringReplace">
                <xsl:with-param name="string" select="$rest"/>
                <xsl:with-param name="from" select="'#20'"/>
                <xsl:with-param name="to" select="' '"/>
              </xsl:call-template>
            </xsl:with-param>
          </xsl:call-template>
          <xsl:text>]</xsl:text>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:if>
    <xsl:if test="string-length($rest) = 0"><xsl:text>]</xsl:text></xsl:if>
  </xsl:template>

  <xsl:template name="displayHyperlink">
    <xsl:param name="href"/>
    <xsl:param name="anchor"/>
    <xsl:param name="title"/>
    <xsl:choose>
      <xsl:when test="$href">
        <a class="external">
          <xsl:attribute name="href"><xsl:value-of select="concat($href, $anchor)"/></xsl:attribute>
          <xsl:value-of select="$title"/>
        </a>
        <xsl:call-template name="displayImage"/>
        <xsl:text> </xsl:text>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$title"/>
        <xsl:call-template name="displayImage"/>
        <xsl:text> </xsl:text>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template name="linkParentDomain">
    <xsl:if test="starts-with(@Name, 'SUPP')">
      <xsl:variable name="parentDatasetName" select="substring(@Name, 5)"/>
      <xsl:if test="../odm:ItemGroupDef[@Name = $parentDatasetName]">
        <xsl:variable name="datasetOID" select="../odm:ItemGroupDef[@Name = $parentDatasetName]/@OID"/>
        <tr>
          <td colspan="8">
            <xsl:text>Related Parent Dataset: </xsl:text>
            <a>
              <xsl:attribute name="href">#IG.<xsl:value-of select="$datasetOID"/></xsl:attribute>
              <xsl:value-of select="$parentDatasetName"/>
            </a>
            <xsl:text> (</xsl:text>
            <xsl:value-of select="//odm:ItemGroupDef[@OID = $datasetOID]/odm:Description/odm:TranslatedText"/>
            <xsl:text>)</xsl:text>
          </td>
        </tr>
      </xsl:if>
    </xsl:if>
  </xsl:template>

  <xsl:template name="linkApParentDomain">
    <xsl:if test="starts-with(@Name, 'SQAP')">
      <xsl:variable name="parentDatasetName" select="concat('AP', substring(@Name, 5))"/>
      <xsl:if test="../odm:ItemGroupDef[@Name = $parentDatasetName]">
        <xsl:variable name="datasetOID" select="../odm:ItemGroupDef[@Name = $parentDatasetName]/@OID"/>
        <tr>
          <td colspan="8">
            <xsl:text>Related Parent Dataset: </xsl:text>
            <a>
              <xsl:attribute name="href">#IG.<xsl:value-of select="$datasetOID"/></xsl:attribute>
              <xsl:value-of select="$parentDatasetName"/>
            </a>
            <xsl:text> (</xsl:text>
            <xsl:value-of select="//odm:ItemGroupDef[@OID = $datasetOID]/odm:Description/odm:TranslatedText"/>
            <xsl:text>)</xsl:text>
          </td>
        </tr>
      </xsl:if>
    </xsl:if>
  </xsl:template>

  <xsl:template name="linkSuppQual">
    <xsl:variable name="suppDatasetName" select="concat('SUPP', @Name)"/>
    <xsl:if test="../odm:ItemGroupDef[@Name = $suppDatasetName]">
      <xsl:variable name="datasetOID" select="../odm:ItemGroupDef[@Name = $suppDatasetName]/@OID"/>
      <tr>
        <td colspan="8">
          <xsl:text>Related Supplemental Qualifiers Dataset: </xsl:text>
          <a>
            <xsl:attribute name="href">#IG.<xsl:value-of select="$datasetOID"/></xsl:attribute>
            <xsl:value-of select="$suppDatasetName"/>
          </a>
          <xsl:text> (</xsl:text>
          <xsl:value-of select="//odm:ItemGroupDef[@OID = $datasetOID]/odm:Description/odm:TranslatedText"/>
          <xsl:text>)</xsl:text>
        </td>
      </tr>
    </xsl:if>
  </xsl:template>

  <xsl:template name="linkSQAP">
    <xsl:if test="substring(@Name, 1, 2)='AP'">
      <xsl:variable name="suppDatasetName" select="concat('SQAP', substring(@Name, 3))"/>
      <xsl:if test="../odm:ItemGroupDef[@Name = $suppDatasetName]">
        <xsl:variable name="datasetOID" select="../odm:ItemGroupDef[@Name = $suppDatasetName]/@OID"/>
        <tr>
          <td colspan="8">
            <xsl:text>Related Supplemental Qualifiers Dataset: </xsl:text>
            <a>
              <xsl:attribute name="href">#IG.<xsl:value-of select="$datasetOID"/></xsl:attribute>
              <xsl:value-of select="$suppDatasetName"/>
            </a>
            <xsl:text> (</xsl:text>
            <xsl:value-of select="//odm:ItemGroupDef[@OID = $datasetOID]/odm:Description/odm:TranslatedText"/>
            <xsl:text>)</xsl:text>
          </td>
        </tr>
      </xsl:if>
    </xsl:if>
  </xsl:template>

  <xsl:template name="getParentDescription">
    <xsl:param name="OID"/>
    <xsl:variable name="Domain" select="$g_seqItemGroupDefs[@OID=$OID]/@Domain"/>
    <xsl:variable name="Name" select="$g_seqItemGroupDefs[@OID=$OID]/@Name"/>
    <xsl:variable name="ParentDescription" select="$g_seqItemGroupDefs[@Domain = $Domain and @Domain = @Name and @Name != $Name]/odm:Description/odm:TranslatedText"/>
    <xsl:choose>
      <xsl:when test="odm:Alias[@Context='DomainDescription']">
        <xsl:value-of select="odm:Alias/@Name"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$ParentDescription"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template name="displayComment">
    <xsl:param name="CommentOID"/>
    <xsl:param name="CommentPrefix"/>
    <xsl:param name="element" select="'p'"/>
    <xsl:if test="$CommentOID">
      <xsl:variable name="Comment" select="$g_seqCommentDefs[@OID=$CommentOID]"/>
      <xsl:variable name="CommentTranslatedText">
        <xsl:value-of select="normalize-space($g_seqCommentDefs[@OID=$CommentOID]/odm:Description/odm:TranslatedText)"/>
      </xsl:variable>
      <xsl:element name="{$element}">
        <xsl:attribute name="class">linebreakcell</xsl:attribute>
        <xsl:choose>
          <xsl:when test="string-length($CommentTranslatedText) &gt; 0">
            <xsl:copy-of select="$PREFIX_COMMENT_TEXT"/>
            <xsl:value-of select="$CommentTranslatedText"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:copy-of select="$PREFIX_COMMENT_TEXT"/>
            <span class="unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$CommentOID"/><xsl:text>]</xsl:text></span>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:element>
      <xsl:for-each select="$Comment/def:DocumentRef">
        <xsl:call-template name="displayDocumentRef">
          <xsl:with-param name="element" select="$element"/>
        </xsl:call-template>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>

  <xsl:template name="displayDescription">
    <xsl:if test="odm:Description/odm:TranslatedText">
      <br/>
      <span class="description"><xsl:value-of select="odm:Description/odm:TranslatedText"/></span>
    </xsl:if>
  </xsl:template>

  <xsl:template name="displayItemDescription">
    <xsl:if test="odm:Description/odm:TranslatedText">
      <span class="itemdescription"><xsl:value-of select="odm:Description/odm:TranslatedText"/></span>
    </xsl:if>
  </xsl:template>

  <xsl:template name="displayItemDefLengthDFormat">
    <xsl:param name="ItemDef"/>
    <xsl:choose>
      <xsl:when test="$ItemDef/@def:DisplayFormat">
        <xsl:value-of select="$ItemDef/@def:DisplayFormat"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$ItemDef/@Length"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template name="displayItemDefLengthSignDigitsDisplayFormat">
    <xsl:param name="ItemDef"/>
    <xsl:choose>
      <xsl:when test="$ItemDef/@Length">
        <xsl:value-of select="$ItemDef/@Length"/>
        <xsl:if test="$ItemDef/@SignificantDigits">
          <xsl:text>  [</xsl:text>
          <xsl:value-of select="$ItemDef/@SignificantDigits"/>
          <xsl:text>]</xsl:text>
        </xsl:if>
        <xsl:if test="$ItemDef/@def:DisplayFormat">
          <xsl:text> : </xsl:text>
          <xsl:value-of select="$ItemDef/@def:DisplayFormat"/>
        </xsl:if>
      </xsl:when>
      <xsl:otherwise>
        <xsl:if test="$ItemDef/@def:DisplayFormat">
          <xsl:value-of select="$ItemDef/@def:DisplayFormat"/>
        </xsl:if>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template name="displayItemDefMethod">
    <xsl:param name="MethodOID"/>
    <xsl:param name="MethodPrefix"/>
    <xsl:if test="$MethodOID">
      <xsl:variable name="Method" select="$g_seqMethodDefs[@OID=$MethodOID]"/>
      <xsl:variable name="MethodTranslatedText" select="$Method/odm:Description/odm:TranslatedText"/>
      <xsl:variable name="MethodFormalExpression" select="$Method/odm:FormalExpression"/>
      <div class="method-code">
        <xsl:choose>
          <xsl:when test="string-length($MethodTranslatedText) &gt; 0">
            <xsl:copy-of select="$PREFIX_METHOD_TEXT"/>
            <xsl:value-of select="$MethodTranslatedText"/>
            <xsl:if test="$MethodFormalExpression">
              <span class="formalexpression-reference">
                <a>
                  <xsl:attribute name="href">#MT.<xsl:value-of select="$MethodOID"/></xsl:attribute>
                  <xsl:attribute name="title">Formal Expression</xsl:attribute>
                  <xsl:text>Formal Expression</xsl:text>
                </a>
              </span>
            </xsl:if>
          </xsl:when>
          <xsl:otherwise>
            <xsl:copy-of select="$PREFIX_METHOD_TEXT"/>
            <span class="unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$MethodOID"/><xsl:text>]</xsl:text></span>
          </xsl:otherwise>
        </xsl:choose>
      </div>
      <xsl:for-each select="$Method/def:DocumentRef">
        <xsl:call-template name="displayDocumentRef"/>
      </xsl:for-each>
    </xsl:if>
  </xsl:template>

  <xsl:template name="displayItemDefOrigin">
    <xsl:param name="itemDef"/>
    <xsl:param name="OriginPrefix"/>
    <xsl:for-each select="$itemDef/def:Origin">
      <xsl:variable name="OriginType" select="@Type"/>
      <xsl:variable name="OriginSource" select="@Source"/>
      <xsl:variable name="OriginDescription" select="./odm:Description/odm:TranslatedText"/>
      <div class="linebreakcell">
        <xsl:copy-of select="$PREFIX_ORIGIN_TEXT"/>
        <xsl:value-of select="$OriginType"/>
        <xsl:if test="$OriginSource">
          <xsl:text> (</xsl:text>
          <span class="linebreakcell">Source: <xsl:value-of select="$OriginSource"/></span>
          <xsl:text>)</xsl:text>
        </xsl:if>
        <xsl:if test="$OriginDescription">
          <xsl:choose>
            <xsl:when test="$OriginSource">
              <p class="linebreakcell"><xsl:value-of select="$OriginDescription"/></p>
            </xsl:when>
            <xsl:otherwise>
              <xsl:choose>
                <xsl:when test="$OriginType = 'Predecessor'">
                  <xsl:text>: </xsl:text>
                  <xsl:value-of select="$OriginDescription"/>
                </xsl:when>
                <xsl:otherwise>
                  <p class="linebreakcell"><xsl:value-of select="$OriginDescription"/></p>
                </xsl:otherwise>
              </xsl:choose>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:if>
      </div>
      <xsl:for-each select="def:DocumentRef">
        <xsl:call-template name="displayDocumentRef"/>
      </xsl:for-each>
      <xsl:if test="position() != last()"><br/></xsl:if>
    </xsl:for-each>
  </xsl:template>

  <xsl:template name="displayItemGroupClass">
    <xsl:if test="@def:Class"><xsl:value-of select="@def:Class"/></xsl:if>
    <xsl:if test="def:Class/@Name">
      <xsl:variable name="ClassName" select="def:Class/@Name"/>
      <xsl:value-of select="$ClassName"/>
      <xsl:if test="def:Class/def:SubClass/@Name">
        <ul class="SubClass">
          <xsl:for-each select="def:Class/def:SubClass[@ParentClass=$ClassName or not(@ParentClass)]">
            <li class="SubClass"><xsl:value-of select="@Name"/></li>
          </xsl:for-each>
        </ul>
      </xsl:if>
    </xsl:if>
  </xsl:template>

  <xsl:template name="displayItemGroupKeys">
    <xsl:variable name="datasetName" select="@Name"/>
    <xsl:variable name="suppDatasetName" select="concat('SUPP', $datasetName)"/>
    <xsl:variable name="sqDatasetName" select="concat('SQ', $datasetName)"/>
    <xsl:variable name="ItemDef" select="$g_seqItemDefs[@Name='QVAL']"/>
    <xsl:variable name="ItemDefValueListOID" select="$ItemDef[@OID=$g_seqItemGroupDefs[@Name = $suppDatasetName or @Name = $sqDatasetName]/odm:ItemRef/@ItemOID]/def:ValueListRef/@ValueListOID"/>
    <xsl:for-each select="odm:ItemRef|$g_seqValueListDefs[@OID=$ItemDefValueListOID]/odm:ItemRef">
      <xsl:sort select="@KeySequence" data-type="number" order="ascending"/>
      <xsl:if test="@KeySequence[ .!='' ]">
        <xsl:variable name="ItemOID" select="@ItemOID"/>
        <xsl:variable name="Name" select="$g_seqItemDefs[@OID=$ItemOID]"/>
        <xsl:if test="../@OID = $ItemDefValueListOID">QNAM.</xsl:if>
        <xsl:value-of select="$Name/@Name"/>
        <xsl:if test="position() != last()">, </xsl:if>
      </xsl:if>
    </xsl:for-each>
  </xsl:template>

  <xsl:template name="displayItemGroupDefHeader">
    <xsl:value-of select="concat(@Name, ' (', ./odm:Description/odm:TranslatedText)"/>
    <xsl:variable name="ParentDescription">
      <xsl:call-template name="getParentDescription">
        <xsl:with-param name="OID" select="@OID"/>
      </xsl:call-template>
    </xsl:variable>
    <xsl:if test="string-length(normalize-space($ParentDescription)) &gt; 0">
      <xsl:text>, </xsl:text><xsl:value-of select="$ParentDescription"/>
    </xsl:if>
    <xsl:text>) - </xsl:text>
    <xsl:value-of select="@def:Class"/><xsl:text> </xsl:text>
    <xsl:call-template name="displayStandard">
      <xsl:with-param name="element" select="'span'"/>
    </xsl:call-template>
    <xsl:call-template name="displayNonStandard">
      <xsl:with-param name="element" select="'span'"/>
    </xsl:call-template>
    <xsl:call-template name="displayNoData">
      <xsl:with-param name="element" select="'span'"/>
    </xsl:call-template>
    <xsl:variable name="archiveLocationID" select="@def:ArchiveLocationID"/>
    <xsl:variable name="archiveTitle">
      <xsl:choose>
        <xsl:when test="def:leaf[@ID=$archiveLocationID]">
          <xsl:value-of select="def:leaf[@ID=$archiveLocationID]/def:title"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:text>[unresolved: </xsl:text><xsl:value-of select="@def:ArchiveLocationID"/><xsl:text>]</xsl:text>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:if test="@def:ArchiveLocationID">
      <span class="dataset">
        <xsl:text>Location: </xsl:text>
        <xsl:call-template name="displayHyperlink">
          <xsl:with-param name="href" select="def:leaf[@ID=$archiveLocationID]/@xlink:href"/>
          <xsl:with-param name="anchor" select="''"/>
          <xsl:with-param name="title" select="$archiveTitle"/>
        </xsl:call-template>
      </span>
    </xsl:if>
  </xsl:template>

  <xsl:template name="displayStandard">
    <xsl:param name="element" select="'p'"/>
    <xsl:variable name="StandardOID" select="@def:StandardOID"/>
    <xsl:variable name="Standard" select="$g_seqStandard[@OID=$StandardOID]"/>
    <xsl:if test="$StandardOID">
      <xsl:element name="{$element}">
        <xsl:attribute name="class">standard-refeference</xsl:attribute>
        <xsl:text>[</xsl:text>
        <xsl:value-of select="$Standard/@Name"/><xsl:text> </xsl:text>
        <xsl:if test="$Standard/@PublishingSet">
          <xsl:value-of select="$Standard/@PublishingSet"/><xsl:text> </xsl:text>
        </xsl:if>
        <xsl:value-of select="$Standard/@Version"/>
        <xsl:text>]</xsl:text>
      </xsl:element>
    </xsl:if>
  </xsl:template>

  <xsl:template name="displayNonStandard">
    <xsl:param name="element" select="'p'"/>
    <xsl:if test="@def:IsNonStandard='Yes'">
      <xsl:element name="{$element}">
        <xsl:attribute name="class">standard-refeference</xsl:attribute>
        <xsl:text>[Non Standard]</xsl:text>
      </xsl:element>
    </xsl:if>
  </xsl:template>

  <xsl:template name="displayNoData">
    <xsl:param name="element" select="'p'"/>
    <xsl:if test="@def:HasNoData='Yes'">
      <xsl:element name="{$element}">
        <xsl:attribute name="class">nodata</xsl:attribute>
        <xsl:text>[No Data]</xsl:text>
      </xsl:element>
    </xsl:if>
  </xsl:template>

  <xsl:template name="displayWhereClause">
    <xsl:param name="ValueItemRef"/>
    <xsl:param name="ItemGroupLink"/>
    <xsl:param name="decode"/>
    <xsl:param name="break"/>
    <xsl:variable name="ValueRef" select="$ValueItemRef"/>
    <xsl:variable name="Nwhereclauses" select="count(./def:WhereClauseRef)"/>
    <xsl:for-each select="$ValueRef/def:WhereClauseRef">
      <xsl:if test="$Nwhereclauses &gt; 1"><xsl:text>(</xsl:text></xsl:if>
      <xsl:variable name="whereOID" select="./@WhereClauseOID"/>
      <xsl:variable name="whereDef" select="$g_seqWhereClauseDefs[@OID=$whereOID]"/>
      <xsl:if test="count($g_seqWhereClauseDefs[@OID=$whereOID])=0">
        <span class="unresolved">[unresolved: <xsl:value-of select="$whereOID"/>]</span>
      </xsl:if>
      <xsl:for-each select="$whereDef/odm:RangeCheck">
        <xsl:variable name="whereRefItemOID" select="./@def:ItemOID"/>
        <xsl:variable name="whereRefItemName" select="$g_seqItemDefs[@OID=$whereRefItemOID]/@Name"/>
        <xsl:variable name="whereOP" select="./@Comparator"/>
        <xsl:variable name="whereRefItemCodeListOID" select="$g_seqItemDefs[@OID=$whereRefItemOID]/odm:CodeListRef/@CodeListOID"/>
        <xsl:variable name="whereRefItemCodeList" select="$g_seqCodeLists[@OID=$whereRefItemCodeListOID]"/>
        <xsl:call-template name="ItemGroupItemLink">
          <xsl:with-param name="ItemGroupOID" select="$ItemGroupLink"/>
          <xsl:with-param name="ItemOID" select="$whereRefItemOID"/>
          <xsl:with-param name="ItemName" select="$whereRefItemName"/>
        </xsl:call-template>
        <xsl:choose>
          <xsl:when test="$whereOP = 'IN' or $whereOP = 'NOTIN'">
            <xsl:text> </xsl:text>
            <xsl:variable name="Nvalues" select="count(./odm:CheckValue)"/>
            <xsl:choose>
              <xsl:when test="$whereOP='IN'"><xsl:text>IN</xsl:text></xsl:when>
              <xsl:otherwise><xsl:text>NOT IN</xsl:text></xsl:otherwise>
            </xsl:choose>
            <xsl:text> (</xsl:text>
            <xsl:if test="$decode='1'"><br/></xsl:if>
            <xsl:for-each select="./odm:CheckValue">
              <xsl:variable name="CheckValueINNOTIN" select="."/>
              <span class="linebreakcell">
                <xsl:call-template name="displayValue">
                  <xsl:with-param name="Value" select="$CheckValueINNOTIN"/>
                  <xsl:with-param name="DataType" select="$g_seqItemDefs[@OID=$whereRefItemOID]/@DataType"/>
                  <xsl:with-param name="decode" select="$decode"/>
                  <xsl:with-param name="CodeList" select="$whereRefItemCodeList"/>
                </xsl:call-template>
                <xsl:if test="position() != $Nvalues"><xsl:value-of select="', '"/></xsl:if>
              </span>
              <xsl:if test="$decode='1'"><br/></xsl:if>
            </xsl:for-each>
            <xsl:text>) </xsl:text>
          </xsl:when>
          <xsl:when test="$whereOP = 'EQ'">
            <xsl:variable name="CheckValueEQ" select="./odm:CheckValue"/>
            <xsl:value-of select="$Comparator_EQ"/>
            <xsl:call-template name="displayValue">
              <xsl:with-param name="Value" select="$CheckValueEQ"/>
              <xsl:with-param name="DataType" select="$g_seqItemDefs[@OID=$whereRefItemOID]/@DataType"/>
              <xsl:with-param name="decode" select="$decode"/>
              <xsl:with-param name="CodeList" select="$whereRefItemCodeList"/>
            </xsl:call-template>
          </xsl:when>
          <xsl:when test="$whereOP = 'NE'">
            <xsl:variable name="CheckValueNE" select="./odm:CheckValue"/>
            <xsl:value-of select="$Comparator_NE"/>
            <xsl:call-template name="displayValue">
              <xsl:with-param name="Value" select="$CheckValueNE"/>
              <xsl:with-param name="DataType" select="$g_seqItemDefs[@OID=$whereRefItemOID]/@DataType"/>
              <xsl:with-param name="decode" select="$decode"/>
              <xsl:with-param name="CodeList" select="$whereRefItemCodeList"/>
            </xsl:call-template>
          </xsl:when>
          <xsl:otherwise>
            <xsl:variable name="CheckValueOTH" select="./odm:CheckValue"/>
            <xsl:text> </xsl:text>
            <xsl:choose>
              <xsl:when test="$whereOP='LT'"><xsl:value-of select="$Comparator_LT"/></xsl:when>
              <xsl:when test="$whereOP='LE'"><xsl:value-of select="$Comparator_LE"/></xsl:when>
              <xsl:when test="$whereOP='GT'"><xsl:value-of select="$Comparator_GT"/></xsl:when>
              <xsl:when test="$whereOP='GE'"><xsl:value-of select="$Comparator_GE"/></xsl:when>
              <xsl:otherwise><xsl:value-of select="$whereOP"/></xsl:otherwise>
            </xsl:choose>
            <xsl:call-template name="displayValue">
              <xsl:with-param name="Value" select="$CheckValueOTH"/>
              <xsl:with-param name="DataType" select="$g_seqItemDefs[@OID=$whereRefItemOID]/@DataType"/>
              <xsl:with-param name="decode" select="$decode"/>
              <xsl:with-param name="CodeList" select="$whereRefItemCodeList"/>
            </xsl:call-template>
          </xsl:otherwise>
        </xsl:choose>
        <xsl:if test="position() != last()">
          <xsl:text> and </xsl:text>
          <xsl:if test="$break='1'"><br/></xsl:if>
        </xsl:if>
      </xsl:for-each>
      <xsl:if test="$Nwhereclauses &gt; 1"><xsl:text>)</xsl:text></xsl:if>
      <xsl:if test="position() != last()">
        <br/><xsl:text> or </xsl:text><br/>
      </xsl:if>
    </xsl:for-each>
  </xsl:template>

  <xsl:template name="displayValue">
    <xsl:param name="Value"/>
    <xsl:param name="DataType"/>
    <xsl:param name="decode"/>
    <xsl:param name="CodeList"/>
    <xsl:if test="$DataType != 'integer' and $DataType != 'float'">
      <xsl:text>"</xsl:text><xsl:value-of select="$Value"/><xsl:text>"</xsl:text>
    </xsl:if>
    <xsl:if test="$DataType = 'integer' or $DataType = 'float'">
      <xsl:value-of select="$Value"/>
    </xsl:if>
    <xsl:if test="$decode='1'">
      <xsl:if test="$CodeList/odm:CodeListItem[@CodedValue=$Value]">
        <xsl:text> (</xsl:text>
        <xsl:value-of select="$CodeList/odm:CodeListItem[@CodedValue=$Value]/odm:Decode/odm:TranslatedText"/>
        <xsl:text>)</xsl:text>
      </xsl:if>
    </xsl:if>
  </xsl:template>

  <xsl:template name="ItemGroupItemLink">
    <xsl:param name="ItemGroupOID"/>
    <xsl:param name="ItemOID"/>
    <xsl:param name="ItemName"/>
    <xsl:choose>
      <xsl:when test="$g_seqItemGroupDefs[@OID=$ItemGroupOID]/odm:ItemRef[@ItemOID=$ItemOID]">
        <xsl:variable name="ItemDescription" select="$g_seqItemDefs[@OID=$ItemOID]/odm:Description/odm:TranslatedText"/>
        <a>
          <xsl:attribute name="href">#<xsl:value-of select="$ItemGroupOID"/>.<xsl:value-of select="$ItemOID"/></xsl:attribute>
          <xsl:attribute name="title"><xsl:value-of select="$ItemDescription"/></xsl:attribute>
          <xsl:value-of select="$ItemName"/>
        </a>
      </xsl:when>
      <xsl:otherwise>
        <xsl:variable name="linkItems" select="count($g_seqItemGroupDefs/odm:ItemRef[@ItemOID=$ItemOID])"/>
        <xsl:choose>
          <xsl:when test="$linkItems = 1">
            <xsl:variable name="ItemDescription" select="$g_seqItemDefs[@OID=$ItemOID]/odm:Description/odm:TranslatedText"/>
            <a>
              <xsl:attribute name="href">#<xsl:value-of select="$g_seqItemGroupDefs/odm:ItemRef[@ItemOID=$ItemOID]/../@OID"/>.<xsl:value-of select="$ItemOID"/></xsl:attribute>
              <xsl:attribute name="title"><xsl:value-of select="$ItemDescription"/></xsl:attribute>
              <xsl:value-of select="$ItemName"/>
            </a>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="$ItemName"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:otherwise>
    </xsl:choose>
    <xsl:if test="string-length(normalize-space($ItemName))=0">
      <span class="unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$ItemOID"/><xsl:text>]</xsl:text></span>
    </xsl:if>
  </xsl:template>

  <!-- Always emit full codelist items; JS limits visible count -->
  <xsl:template name="displayItemDefDecodeList">
    <xsl:param name="itemDef"/>
    <xsl:variable name="CodeListOID" select="$itemDef/odm:CodeListRef/@CodeListOID"/>
    <xsl:variable name="CodeListDef" select="$g_seqCodeLists[@OID=$CodeListOID]"/>
    <xsl:variable name="n_items" select="count($CodeListDef/odm:CodeListItem|$CodeListDef/odm:EnumeratedItem)"/>
    <xsl:variable name="CodeListDataType" select="$CodeListDef/@DataType"/>
    <xsl:if test="$itemDef/odm:CodeListRef">
      <xsl:choose>
        <xsl:when test="$CodeListDef/odm:CodeListItem or $CodeListDef/odm:EnumeratedItem">
          <span class="linebreakcell">
            <xsl:choose>
              <xsl:when test="$g_seqCodeLists[@OID=$CodeListOID]">
                <a href="#CL.{$CodeListDef/@OID}"><xsl:value-of select="$CodeListDef/@Name"/></a>
              </xsl:when>
              <xsl:otherwise>
                <span class="unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$CodeListOID"/><xsl:text>]</xsl:text></span>
              </xsl:otherwise>
            </xsl:choose>
          </span>
          <ul class="codelist" data-codelist-items="all">
            <xsl:for-each select="$CodeListDef/odm:CodeListItem">
              <li class="codelist-item">
                <xsl:if test="$CodeListDataType='text'">
                  <xsl:text>&#8226;&#160;</xsl:text><xsl:value-of select="concat('&quot;', @CodedValue, '&quot;')"/>
                </xsl:if>
                <xsl:if test="$CodeListDataType != 'text'">
                  <xsl:text>&#8226;&#160;</xsl:text><xsl:value-of select="@CodedValue"/>
                </xsl:if>
                <xsl:text> = </xsl:text>
                <xsl:value-of select="concat('&quot;', odm:Decode/odm:TranslatedText, '&quot;')"/>
              </li>
            </xsl:for-each>
            <xsl:for-each select="$CodeListDef/odm:EnumeratedItem">
              <li class="codelist-item">
                <xsl:if test="$CodeListDataType='text'">
                  <xsl:text>&#8226;&#160;</xsl:text><xsl:value-of select="concat('&quot;', @CodedValue, '&quot;')"/>
                </xsl:if>
                <xsl:if test="$CodeListDataType != 'text'">
                  <xsl:text>&#8226;&#160;</xsl:text><xsl:value-of select="@CodedValue"/>
                </xsl:if>
              </li>
            </xsl:for-each>
          </ul>
          <xsl:if test="$n_items &gt; 0">
            <p class="linebreakcell codelist-count">
              <xsl:text>[</xsl:text>
              <xsl:value-of select="$n_items"/>
              <xsl:choose>
                <xsl:when test="$n_items &gt; 1"><xsl:text> Terms]</xsl:text></xsl:when>
                <xsl:otherwise><xsl:text> Term]</xsl:text></xsl:otherwise>
              </xsl:choose>
            </p>
          </xsl:if>
        </xsl:when>
        <xsl:otherwise>
          <xsl:choose>
            <xsl:when test="$g_seqCodeLists[@OID=$CodeListOID]">
              <a href="#CL.{$CodeListDef/@OID}"><xsl:value-of select="$CodeListDef/@Name"/></a>
            </xsl:when>
            <xsl:otherwise>
              <span class="unresolved"><xsl:text>[unresolved: </xsl:text><xsl:value-of select="$itemDef/odm:CodeListRef/@CodeListOID"/><xsl:text>]</xsl:text></span>
            </xsl:otherwise>
          </xsl:choose>
          <xsl:if test="$CodeListDef/odm:ExternalCodeList">
            <p class="linebreakcell">
              <xsl:value-of select="$CodeListDef/odm:ExternalCodeList/@Dictionary"/>
              <xsl:text> </xsl:text>
              <xsl:value-of select="$CodeListDef/odm:ExternalCodeList/@Version"/>
            </p>
          </xsl:if>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:if>
  </xsl:template>

  <xsl:template name="setRowClassOddeven">
    <xsl:param name="rowNum"/>
    <xsl:attribute name="class">
      <xsl:choose>
        <xsl:when test="$rowNum mod 2 = 0"><xsl:text>tableroweven</xsl:text></xsl:when>
        <xsl:otherwise><xsl:text>tablerowodd</xsl:text></xsl:otherwise>
      </xsl:choose>
    </xsl:attribute>
  </xsl:template>

  <xsl:template name="stringReplace">
    <xsl:param name="string"/>
    <xsl:param name="from"/>
    <xsl:param name="to"/>
    <xsl:choose>
      <xsl:when test="contains($string,$from)">
        <xsl:value-of select="substring-before($string,$from)"/>
        <xsl:copy-of select="$to"/>
        <xsl:call-template name="stringReplace">
          <xsl:with-param name="string" select="substring-after($string,$from)"/>
          <xsl:with-param name="from" select="$from"/>
          <xsl:with-param name="to" select="$to"/>
        </xsl:call-template>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$string"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template name="displayItemDefISO8601">
    <xsl:param name="itemDef"/>
    <xsl:if test="$itemDef/@DataType='date' or $itemDef/@DataType='time' or $itemDef/@DataType='datetime' or $itemDef/@DataType='partialDate' or $itemDef/@DataType='partialTime' or $itemDef/@DataType='partialDatetime' or $itemDef/@DataType='incompleteDatetime' or $itemDef/@DataType='durationDatetime'">
      <xsl:text>ISO 8601</xsl:text>
    </xsl:if>
  </xsl:template>

  <xsl:template name="lineBreak">
    <xsl:element name="br">
      <xsl:call-template name="noBreakSpace"/>
    </xsl:element>
  </xsl:template>

  <xsl:template name="noBreakSpace">
    <xsl:text/>
  </xsl:template>

  <xsl:template name="displayButtons">
    <xsl:if test="$g_seqValueListDefs">
      <div class="buttons">
        <div class="button"><button type="button" onclick="expand_all_vlm();">Expand all VLM</button></div>
        <div class="button"><button type="button" onclick="collapse_all_vlm();">Collapse all VLM</button></div>
      </div>
    </xsl:if>
  </xsl:template>

  <xsl:template name="linkTop">
    <p class="linktop">Go to the <a href="#main">top</a> of the Define-XML document</p>
  </xsl:template>

  <xsl:template name="displayImage">
    <span class="external-link-gif"/>
  </xsl:template>

  <xsl:template name="displaySystemProperties">
    <xsl:text>&#xA;</xsl:text>
    <xsl:comment>
      <xsl:text>&#xA;     xsl:version = "</xsl:text>
      <xsl:value-of select="system-property('xsl:version')"/>
      <xsl:text>"&#xA;     xsl:vendor = "</xsl:text>
      <xsl:value-of select="system-property('xsl:vendor')"/>
      <xsl:text>"&#xA;     xsl:vendor-url = "</xsl:text>
      <xsl:value-of select="system-property('xsl:vendor-url')"/>
      <xsl:text>"&#xA;   </xsl:text>
    </xsl:comment>
    <xsl:text>&#xA;</xsl:text>
  </xsl:template>

  <xsl:template name="displayODMCreationDateTimeDate">
    <p class="documentinfo">Date/Time of Define-XML document generation: <xsl:value-of select="/odm:ODM/@CreationDateTime"/></p>
  </xsl:template>

  <xsl:template name="displayContext">
    <xsl:if test="/odm:ODM/@def:Context">
      <p class="documentinfo">Define-XML Context: <xsl:value-of select="/odm:ODM/@def:Context"/></p>
    </xsl:if>
  </xsl:template>

  <xsl:template name="displayDefineXMLVersion">
    <p class="documentinfo">Define-XML version: <xsl:value-of select="$g_DefineVersion"/></p>
  </xsl:template>

  <xsl:template name="displayStylesheetDate">
    <p class="stylesheetinfo">Stylesheet version: <xsl:value-of select="$STYLESHEET_VERSION"/></p>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- JavaScript                                           -->
  <!-- **************************************************** -->
  <xsl:template name="generateJavaScript">
<script><![CDATA[
(function () {
  "use strict";

  var ITEM = "\u00A0";
  var CLOSE = "\u25BA";
  var OPEN = "\u25BC";

  function textContent(el, value) {
    if (value === undefined) {
      return el.textContent !== undefined ? el.textContent : el.innerText;
    }
    if (el.textContent !== undefined) {
      el.textContent = value;
    } else {
      el.innerText = value;
    }
  }

  function toggleSubmenu(bullet) {
    var isOpen = textContent(bullet) === OPEN;
    textContent(bullet, isOpen ? CLOSE : OPEN);
    var parent = bullet.parentNode;
    if (!parent) return;
    var children = parent.childNodes;
    var i, c;
    for (i = 0; i < children.length; i++) {
      c = children[i];
      if (c.tagName === "UL") {
        var show = c.style.display === "none" || !c.style.display;
        c.style.display = show ? "block" : "none";
        c.setAttribute("aria-hidden", show ? "false" : "true");
      }
    }
  }

  function resetMenus() {
    var liTags = document.getElementsByTagName("LI");
    var i, j, li, c;
    for (i = 0; i < liTags.length; i++) {
      li = liTags[i];
      if (li.className.indexOf("hmenu-item") !== -1) {
        for (j = 0; j < li.childNodes.length; j++) {
          c = li.childNodes[j];
          if (c.tagName === "SPAN" && c.className.indexOf("hmenu-bullet") !== -1) {
            textContent(c, ITEM);
          }
        }
      }
      if (li.className.indexOf("hmenu-submenu") !== -1) {
        for (j = 0; j < li.childNodes.length; j++) {
          c = li.childNodes[j];
          if (c.tagName === "SPAN" && c.className.indexOf("hmenu-bullet") !== -1) {
            textContent(c, CLOSE);
          } else if (c.tagName === "UL") {
            c.style.display = "none";
            c.setAttribute("aria-hidden", "true");
          }
        }
      }
    }
  }

  function toggleVlm(element) {
    var anchor = element.querySelector ? element.querySelector("a") : null;
    if (!anchor && element.childNodes && element.childNodes[0]) {
      anchor = element.childNodes[0];
    }
    if (!anchor) return;
    var childId = anchor.getAttribute("id");
    if (!childId) return;
    var rows = document.getElementsByClassName(childId);
    var j, show = null;
    for (j = 0; j < rows.length; j++) {
      if (show === null) {
        show = rows[j].style.display === "none" || rows[j].style.display === "";
        if (rows[j].style.display === "") {
          show = window.getComputedStyle(rows[j]).display === "none";
        }
      }
      rows[j].style.display = show ? "table-row" : "none";
    }
  }

  function expandAllVlm() {
    var rows = document.getElementsByClassName("vlm");
    var j;
    for (j = 0; j < rows.length; j++) {
      rows[j].style.display = "table-row";
    }
  }

  function collapseAllVlm() {
    var rows = document.getElementsByClassName("vlm");
    var j;
    for (j = 0; j < rows.length; j++) {
      rows[j].style.display = "none";
    }
  }

  function setSidebarOpen(open) {
    var toggle = document.getElementById("menu-toggle");
    var overlay = document.getElementById("sidebar-overlay");
    document.body.classList.toggle("sidebar-open", open);
    if (toggle) toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (overlay) {
      if (open) overlay.removeAttribute("hidden");
      else overlay.setAttribute("hidden", "hidden");
    }
  }

  function initSidebar() {
    var toggle = document.getElementById("menu-toggle");
    var overlay = document.getElementById("sidebar-overlay");
    if (toggle) {
      toggle.addEventListener("click", function () {
        setSidebarOpen(!document.body.classList.contains("sidebar-open"));
      });
    }
    if (overlay) {
      overlay.addEventListener("click", function () {
        setSidebarOpen(false);
      });
    }
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setSidebarOpen(false);
    });
  }

  function applyDefineSettings() {
    var nEl = document.getElementById("opt-nCodeListItemDisplay");
    var methodsEl = document.getElementById("opt-displayMethodsTable");
    var commentsEl = document.getElementById("opt-displayCommentsTable");
    var prefixEl = document.getElementById("opt-displayPrefix");
    var lengthEl = document.getElementById("opt-displayLengthDFormatSD");

    var n = nEl ? parseInt(nEl.value, 10) : 5;
    if (isNaN(n) || n < 0) n = 0;

    document.body.classList.toggle("hide-methods", !(methodsEl && methodsEl.checked));
    document.body.classList.toggle("hide-comments", !(commentsEl && commentsEl.checked));
    document.body.classList.toggle("hide-prefix", !(prefixEl && prefixEl.checked));
    document.body.classList.toggle("length-full", !!(lengthEl && lengthEl.checked));
    document.body.classList.toggle("length-simple", !(lengthEl && lengthEl.checked));

    var lists = document.querySelectorAll("ul.codelist");
    var i, j, items;
    for (i = 0; i < lists.length; i++) {
      items = lists[i].querySelectorAll(":scope > li.codelist-item");
      for (j = 0; j < items.length; j++) {
        if (n === 0) {
          items[j].classList.add("is-hidden-by-limit");
        } else if (n >= 999) {
          items[j].classList.remove("is-hidden-by-limit");
        } else {
          items[j].classList.toggle("is-hidden-by-limit", j >= n);
        }
      }
    }

    try {
      localStorage.setItem("defineXmlSettings", JSON.stringify({
        n: n,
        methods: !!(methodsEl && methodsEl.checked),
        comments: !!(commentsEl && commentsEl.checked),
        prefix: !!(prefixEl && prefixEl.checked),
        lengthSD: !!(lengthEl && lengthEl.checked)
      }));
    } catch (err) { /* ignore */ }
  }

  function loadDefineSettings() {
    try {
      var raw = localStorage.getItem("defineXmlSettings");
      if (!raw) return;
      var s = JSON.parse(raw);
      var nEl = document.getElementById("opt-nCodeListItemDisplay");
      var methodsEl = document.getElementById("opt-displayMethodsTable");
      var commentsEl = document.getElementById("opt-displayCommentsTable");
      var prefixEl = document.getElementById("opt-displayPrefix");
      var lengthEl = document.getElementById("opt-displayLengthDFormatSD");
      if (nEl && s.n != null) nEl.value = s.n;
      if (methodsEl && s.methods != null) methodsEl.checked = s.methods;
      if (commentsEl && s.comments != null) commentsEl.checked = s.comments;
      if (prefixEl && s.prefix != null) prefixEl.checked = s.prefix;
      if (lengthEl && s.lengthSD != null) lengthEl.checked = s.lengthSD;
    } catch (err) { /* ignore */ }
  }

  window.toggle_submenu = toggleSubmenu;
  window.reset_menus = resetMenus;
  window.toggle_vlm = toggleVlm;
  window.expand_all_vlm = expandAllVlm;
  window.collapse_all_vlm = collapseAllVlm;

  document.addEventListener("DOMContentLoaded", function () {
    resetMenus();
    initSidebar();
    collapseAllVlm();
    loadDefineSettings();
    applyDefineSettings();
    var form = document.getElementById("settings-form");
    if (form) {
      form.addEventListener("change", applyDefineSettings);
      form.addEventListener("input", applyDefineSettings);
    }
  });

  document.addEventListener("click", function (e) {
    var target = e.target;
    while (target && target !== document.body && target.nodeName !== "A") {
      target = target.parentNode;
    }
    if (target && target.className && String(target.className).indexOf("external") !== -1) {
      e.preventDefault();
      window.open(target.href, "_blank", "noopener,noreferrer");
    }
  });
})();
]]></script>
  </xsl:template>

  <!-- **************************************************** -->
  <!-- CSS                                                  -->
  <!-- **************************************************** -->
  <xsl:template name="generateCSS">
<style><![CDATA[
:root {
  --bg: #f6f7f9;
  --surface: #ffffff;
  --surface-muted: #f1f3f5;
  --surface-accent: #eef4ff;
  --text: #172033;
  --text-muted: #647084;
  --border: #dfe4ec;
  --border-strong: #cbd3df;
  --accent: #315fce;
  --accent-hover: #244aa8;
  --accent-soft: #e8efff;
  --warning: #9a6700;
  --danger: #c62828;
  --header: #253b68;
  --header-text: #ffffff;
  --vlm: #f4f6f9;
  --shadow: 0 8px 30px rgba(23, 32, 51, 0.07);
  --radius: 12px;
  --radius-sm: 8px;
  --sidebar-width: 300px;
  --content-max: 1800px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1419;
    --surface: #1a2332;
    --surface-muted: #151c28;
    --surface-accent: #1e2a3d;
    --text: #e8edf5;
    --text-muted: #9aa8bc;
    --border: #2a3548;
    --border-strong: #3a4a63;
    --accent: #6b9aff;
    --accent-hover: #8cb0ff;
    --accent-soft: #1e2d4a;
    --header: #1e3a5f;
    --header-text: #f0f4fa;
    --vlm: #1a2433;
    --shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
  }
}
*, *::before, *::after { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 24px; }
body {
  margin: 0; padding: 0; background: var(--bg); color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 14px; line-height: 1.55;
}
.visually-hidden {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
}
.skip-link {
  position: absolute; left: -9999px; top: 0; z-index: 100;
  padding: 8px 14px; background: var(--accent); color: #fff; border-radius: 6px; font-weight: 600;
}
.skip-link:focus { left: 12px; top: 12px; }
a { color: var(--accent); text-decoration: none; text-underline-offset: 3px; }
a:hover { color: var(--accent-hover); text-decoration: underline; }
a:focus-visible, button:focus-visible {
  outline: 3px solid rgba(49, 95, 206, 0.35); outline-offset: 2px; border-radius: 5px;
}

.settings-panel {
  margin: 0 0 24px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow); max-width: 440px;
}
.settings-panel summary {
  padding: 12px 16px; font-weight: 700; cursor: pointer; user-select: none;
}
.settings-form { display: flex; flex-direction: column; gap: 10px; padding: 0 16px 16px; }
.settings-row {
  display: flex; align-items: center; gap: 10px; font-size: 13px; cursor: pointer;
}
.settings-row input[type="number"] {
  width: 4.5rem; margin-left: auto; padding: 4px 8px;
  border: 1px solid var(--border-strong); border-radius: 6px;
  background: var(--surface-muted); color: var(--text); font: inherit;
}
.settings-hint { margin: 4px 0 0; font-size: 11px; color: var(--text-muted); }

body.hide-methods .section-methods,
body.hide-methods [data-section="methods"] { display: none !important; }
body.hide-comments .section-comments,
body.hide-comments [data-section="comments"] { display: none !important; }
body.hide-prefix .prefix { display: none !important; }
body.length-simple .length-full,
body.length-simple .length-header-full { display: none !important; }
body.length-full .length-simple,
body.length-full .length-header-simple { display: none !important; }
.codelist-item.is-hidden-by-limit { display: none !important; }

.menu-toggle {
  display: none; position: fixed; top: 12px; left: 12px; z-index: 40;
  width: 44px; height: 44px; padding: 0; border: 1px solid var(--border-strong);
  border-radius: 10px; background: var(--surface); box-shadow: var(--shadow); cursor: pointer;
}
.menu-toggle-bars, .menu-toggle-bars::before, .menu-toggle-bars::after {
  display: block; width: 18px; height: 2px; margin: 0 auto; background: var(--text);
  border-radius: 1px; content: ""; position: relative;
}
.menu-toggle-bars::before { top: -6px; position: absolute; left: 0; }
.menu-toggle-bars::after { top: 6px; position: absolute; left: 0; }
.sidebar-overlay {
  display: none; position: fixed; inset: 0; z-index: 25; background: rgba(15, 20, 25, 0.45);
}

#menu {
  position: fixed; z-index: 30; inset: 0 auto 0 0; width: var(--sidebar-width);
  overflow-y: auto; overflow-x: hidden; padding: 28px 20px 24px;
  background: var(--surface); color: var(--text); border-right: 1px solid var(--border);
  box-shadow: 4px 0 24px rgba(23, 32, 51, 0.04); scrollbar-width: thin;
}
.study-name {
  display: block; margin: 0 4px 24px; padding: 0 0 18px; border-bottom: 1px solid var(--border);
  font-size: 19px; line-height: 1.3; font-weight: 750; letter-spacing: -0.02em;
}
.hmenu, .hmenu ul { margin: 0; padding: 0; }
.hmenu li { list-style: none; margin: 2px 0; line-height: 1.35; }
.hmenu ul { margin: 3px 0 6px 17px; padding-left: 10px; border-left: 1px solid var(--border); }
.hmenu-bullet {
  display: inline-flex; width: 18px; height: 28px; align-items: center; justify-content: center;
  color: var(--text-muted); font-size: 12px; font-weight: 700; cursor: pointer; user-select: none; vertical-align: middle;
}
a.tocItem, .tocItem {
  display: inline-block; max-width: calc(100% - 24px); padding: 5px 7px; color: var(--text);
  font-size: 13px; line-height: 1.35; text-decoration: none; border-radius: 6px; vertical-align: middle;
  transition: background-color .15s ease, color .15s ease;
}
a.tocItem:hover { color: var(--accent-hover); background: var(--accent-soft); text-decoration: none; }
.hmenu > li > a.tocItem { font-weight: 650; }
.unresolved { color: var(--danger); font-weight: 600; }

#main {
  position: relative; width: calc(100% - var(--sidebar-width));
  max-width: calc(var(--content-max) + var(--sidebar-width)); min-height: 100vh;
  margin-left: var(--sidebar-width); padding: 36px 42px 80px; background: var(--bg); color: var(--text);
}
#main > * { max-width: var(--content-max); }
h1 { margin: 44px 0 16px; font-size: 23px; line-height: 1.25; font-weight: 750; letter-spacing: -0.025em; }
h1.invisible, h1.header.invisible {
  position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0);
}
.containerbox { margin: 0 auto 34px; page-break-after: always; }
#main .docinfo {
  display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px 18px;
  margin: 0 0 18px; color: var(--text-muted); font-size: 11px;
}

dl.study-metadata {
  display: grid; grid-template-columns: minmax(150px, 210px) minmax(0, 1fr);
  margin: 0 0 32px; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden;
}
dl.study-metadata dt, dl.study-metadata dd {
  margin: 0; padding: 13px 16px; border-bottom: 1px solid var(--border);
}
dl.study-metadata dt { color: var(--text-muted); background: var(--surface-muted); font-weight: 650; }
dl.study-metadata dd { overflow-wrap: anywhere; }
dl.study-metadata dt:last-of-type, dl.study-metadata dd:last-of-type { border-bottom: 0; }
.description {
  margin: 14px 0 0; padding: 14px 16px; color: var(--text-muted); background: var(--surface);
  border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: var(--radius-sm); font-size: 13px;
}

table {
  width: 100%; border: 1px solid var(--border); border-collapse: separate; border-spacing: 0;
  background: var(--surface); border-radius: var(--radius); box-shadow: var(--shadow);
  overflow: hidden; empty-cells: show;
}
table caption { padding: 0 0 12px; color: var(--text); font-size: 16px; font-weight: 700; text-align: left; }
table caption.header { font-size: 20px; font-weight: 750; }
table caption .dataset { float: right; color: var(--text-muted); font-size: 12px; font-weight: 500; }
table tr.header { background: var(--header); color: var(--header-text); }
table th {
  padding: 11px 13px; border-bottom: 1px solid var(--border-strong);
  font-size: 12px; font-weight: 700; text-align: left; vertical-align: top;
}
table td {
  padding: 10px 13px; border-bottom: 1px solid var(--border);
  font-size: 13px; vertical-align: top;
}
table tr:last-child td { border-bottom: 0; }
table tr.tablerowodd td { background: var(--surface); }
table tr.tableroweven td { background: var(--surface-muted); }
table tr:hover td { background: var(--surface-accent); }
table td.number { text-align: right; font-variant-numeric: tabular-nums; }

ul.codelist { margin: 0; padding: 0; }
.codelist li { list-style: none; margin: 3px 0; }
.codelist-caption { margin: 22px 0 10px; font-size: 15px; font-weight: 700; }
.codelist-item {
  list-style: disc; list-style-position: outside; margin: 0 0 4px 20px;
}
.codelist-item-decode { white-space: pre-wrap; overflow-wrap: anywhere; }
ul.SubClass { margin: 0; padding-left: 20px; list-style-type: "- "; }
div.qval-indent { margin-left: 20px; }
div.qval-indent2 { margin-left: 40px; }

div.buttons { display: flex; flex-wrap: wrap; gap: 8px; margin: 22px 0 0; }
button {
  min-width: 145px; padding: 8px 13px; color: var(--text); background: var(--surface);
  border: 1px solid var(--border-strong); border-radius: 7px;
  box-shadow: 0 1px 2px rgba(23, 32, 51, .05); cursor: pointer; font: inherit;
  font-size: 12px; font-weight: 650;
  transition: background-color .15s ease, border-color .15s ease, transform .15s ease;
}
button:hover { background: var(--surface-accent); transform: translateY(-1px); }

tr.vlm td { background: var(--vlm); }
.valuelist-reference, .valuelist-no-reference, .formalexpression-reference {
  vertical-align: super; margin-left: 3px; color: var(--accent);
  font-size: 10px; font-weight: 700; cursor: pointer;
}
.formalexpression-code, .method-code, .arm-code {
  display: block; margin: 8px 0; padding: 11px 13px; background: var(--surface-muted);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere;
}
.linktop { margin: 16px 0 0; font-size: 12px; }
.standard-refeference { padding: 8px 10px; color: var(--text-muted); font-size: 12px; font-weight: 650; }
.nodata {
  padding: 8px 10px; color: var(--warning); background: #fff8e6;
  border-radius: 6px; font-size: 12px; font-weight: 650;
}
@media (prefers-color-scheme: dark) {
  .nodata { background: #3d3200; color: #f0c040; }
}
span.prefix { color: var(--text-muted); font-weight: 500; }

.arm-summary {
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface);
  box-shadow: var(--shadow); overflow: hidden;
}
.arm-summary-resultdisplay { padding: 14px 16px; border-bottom: 1px solid var(--border); }
.arm-summary-resultdisplay:last-child { border-bottom: 0; }
.arm-display-title { margin-left: 6px; color: var(--text-muted); }
.arm-summary-result { margin: 7px 0 0 22px; }
tr.arm-analysisresult td {
  background: var(--header); color: var(--header-text); font-weight: 700;
}
td.arm-label {
  width: 25%; color: var(--text-muted); background: var(--surface-muted); font-weight: 650;
}
.arm-data-reference {
  margin: 6px 0; padding: 8px 10px; background: var(--surface-muted);
  border: 1px solid var(--border); border-radius: 6px;
}
.external-link-gif {
  background: url(data:image/gif;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAAXNSR0IArs4c6QAAAAlwSFlzAAALEwAACxMBAJqcGAAAAAd0SUlFB9gCGhErDWL4mOoAAAB6SURBVBjTbVCxDcAgDHNRP2KDY9gYO5YbWNno1mPY6E3pAJEIYCmCOCQOPogII6wNkug4d49KiXMz1EiUEg8uLBN3Ui7FVduYmxjG3JRru+facubVuIdLEV4Dzwe8V4BYg7t4Ap+d57qUnuWICBzi116v1ggfd3bM+AEZWXFvnym8EwAAAABJRU5ErkJggg==) no-repeat right center;
  padding-right: 16px;
}

@media (max-width: 1100px) {
  :root { --sidebar-width: 250px; }
  #main { padding: 30px 26px 70px; }
}
@media (max-width: 800px) {
  .menu-toggle { display: flex; align-items: center; justify-content: center; }
  .sidebar-overlay { display: block; }
  body:not(.sidebar-open) .sidebar-overlay { display: none; }
  #menu {
    transform: translateX(-100%); transition: transform .2s ease; width: min(300px, 88vw);
  }
  body.sidebar-open #menu { transform: translateX(0); }
  #main { width: 100%; margin-left: 0; padding: 70px 16px 60px; }
  table { display: block; overflow-x: auto; -webkit-overflow-scrolling: touch; }
  table caption { display: table-caption; }
  dl.study-metadata { grid-template-columns: 1fr; }
  dl.study-metadata dt { padding-bottom: 5px; border-bottom: 0; }
  dl.study-metadata dd { padding-top: 5px; }
  td.arm-label { width: auto; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after {
    transition-duration: 0.01ms !important; animation-duration: 0.01ms !important;
  }
}
@media print {
  @page { margin: 1.5cm; }
  body, #main { color: #000; background: #fff; }
  #menu, .linktop, div.buttons, .menu-toggle, .sidebar-overlay, .settings-panel { display: none !important; }
  #main { width: 100%; margin: 0; padding: 0; }
  .containerbox { page-break-after: always; box-shadow: none; }
  table, dl.study-metadata, .arm-summary { box-shadow: none; border-color: #888; }
  table tr.vlm { display: table-row !important; }
  table th { color: #000; background: #eee; }
  a:link, a:visited { color: #000; text-decoration: none; }
  a.external:link::after { content: " (" attr(href) ") "; font-size: 90%; }
  .external-link-gif, .formalexpression-reference, .valuelist-reference { display: none !important; }
  body.hide-prefix .prefix { display: inline !important; }
  body.length-simple .length-full, body.length-full .length-simple { display: inline !important; }
  .codelist-item.is-hidden-by-limit { display: list-item !important; }
}
]]></style>
  </xsl:template>

  <xsl:template match="/odm:ODM/odm:Study/odm:GlobalVariables"/>
  <xsl:template match="/odm:ODM/odm:Study/odm:BasicDefinitions"/>
  <xsl:template match="/odm:ODM/odm:Study/odm:MetaDataVersion"/>

</xsl:stylesheet>
